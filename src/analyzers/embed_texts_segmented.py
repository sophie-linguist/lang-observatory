"""
세그먼트 단위 임베딩 - texts·comments 통합

5/25 새 설계:
- 본문 앞 512자 한계 → 300자 세그먼트로 잘라 각각 임베딩
- 매체별 비대칭 보정 샘플링:
  * 신문(source_id=6): 1/10 샘플 (약 45만)
  * 일상대화(5)·네이버(3)·유튜브 영상(4): 전체
  * 유튜브 댓글(7): 전체 (5/26부터 새 균형 전략으로 누적될 풀)
- GPU 모드 (bge-m3 fp16, 배치 512)
- texts.embeddings_processed / comments.embeddings_processed 플래그로 진행 추적

5/25 저녁 추가:
- 한 줄 에러로 배치 전체 죽지 않게 (b) 방식 보강
  * 배치 COPY 실패 시 한 줄씩 INSERT 재시도 → 진짜 문제 줄만 건너뜀
  * 백슬래시 이스케이프 추가 (PostgreSQL COPY가 \\N을 NULL로 해석하는 함정 회피)
"""
import os
import sys
import time
import random
import io
from datetime import datetime

import torch
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

MODEL_NAME = "BAAI/bge-m3"
SEGMENT_LEN = 300
BATCH_SIZE = 512  # GPU 배치
RANDOM_SEED = 42

# 매체별 샘플링 비율 (1 = 전체, 10 = 1/10)
SAMPLING = {
    3: 1,   # 네이버 뉴스 — 전체
    4: 1,   # 유튜브 영상 — 전체
    5: 1,   # 일상대화 — 전체
    6: 10,  # 신문 — 1/10
}


def ensure_schema(conn):
    """embeddings 테이블·인덱스 + texts/comments에 진행 플래그 컬럼 추가."""
    cur = conn.cursor()

    # pgvector 확장
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # embeddings 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id    bigserial PRIMARY KEY,
            text_id         bigint,
            comment_id      bigint,
            segment_index   int NOT NULL,
            start_pos       int NOT NULL,
            end_pos         int NOT NULL,
            segment_text    text NOT NULL,
            embedding       vector(1024),
            CHECK (text_id IS NOT NULL OR comment_id IS NOT NULL)
        )
    """)

    # 텍스트·댓글 역인덱스 (단어→세그먼트 매핑 만들 때 씀)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emb_text_id ON embeddings(text_id) WHERE text_id IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emb_comment_id ON embeddings(comment_id) WHERE comment_id IS NOT NULL")

    # 진행 추적 컬럼
    cur.execute("""
        ALTER TABLE texts
        ADD COLUMN IF NOT EXISTS embeddings_processed boolean NOT NULL DEFAULT false
    """)
    cur.execute("""
        ALTER TABLE comments
        ADD COLUMN IF NOT EXISTS embeddings_processed boolean NOT NULL DEFAULT false
    """)

    conn.commit()
    cur.close()
    print("스키마 준비 완료", flush=True)


def make_segments(text, seg_len=SEGMENT_LEN):
    """텍스트를 seg_len 단위 세그먼트로 자름. (segment_index, start, end, segment_text) 튜플 리스트."""
    if not text:
        return []
    segments = []
    n = len(text)
    for i, start in enumerate(range(0, n, seg_len)):
        end = min(start + seg_len, n)
        seg = text[start:end]
        if seg.strip():  # 공백만 있는 세그먼트 거르기
            segments.append((i, start, end, seg))
    return segments


def get_target_texts(conn):
    """매체별 샘플링 적용 후 임베딩 대상 text_id 가져오기.

    embeddings_processed = false 인 것만.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT text_id, source_id, content
        FROM texts
        WHERE embeddings_processed = false
          AND content IS NOT NULL AND content != ''
        ORDER BY text_id
    """)
    all_rows = cur.fetchall()
    cur.close()

    # 매체별 분류 후 샘플링
    by_source = {}
    for tid, sid, content in all_rows:
        by_source.setdefault(sid, []).append((tid, content))

    sampled = []
    random.seed(RANDOM_SEED)
    for sid, rows in by_source.items():
        ratio = SAMPLING.get(sid, 1)
        if ratio == 1:
            sampled.extend(rows)
        else:
            k = len(rows) // ratio
            picked = random.sample(rows, k)
            sampled.extend(picked)
        print(f"  source_id={sid}: 전체 {len(rows):,} → 샘플 {len(rows) // ratio if ratio > 1 else len(rows):,}", flush=True)

    return sampled


def get_target_comments(conn):
    """comments 전체 (5/26부터 새 균형 전략으로 누적될 풀)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT comment_id, content
        FROM comments
        WHERE embeddings_processed = false
          AND content IS NOT NULL AND content != ''
        ORDER BY comment_id
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def copy_batch_with_retry(cur, conn, buf, batch, vectors, kind):
    """배치 COPY 시도. 실패하면 한 줄씩 INSERT로 재시도해서 진짜 문제 줄만 건너뜀.

    kind: 'text' 또는 'comment' — INSERT 시 어느 컬럼에 박을지 구분
    """
    buf.seek(0)
    try:
        cur.copy_from(
            buf, 'embeddings',
            columns=('text_id', 'comment_id', 'segment_index', 'start_pos', 'end_pos', 'segment_text', 'embedding')
        )
        conn.commit()
        return 0  # 0건 건너뜀
    except Exception as e:
        conn.rollback()
        print(f"  [WARN] 배치 COPY 실패 ({len(batch)}건), 한 줄씩 재시도: {type(e).__name__}", flush=True)

    # 한 줄씩 INSERT 재시도
    skipped = 0
    for b, vec in zip(batch, vectors):
        if kind == 'text':
            tid, seg_idx, start, end, seg = b
            vec_str = '[' + ','.join(f"{v:.6f}" for v in vec) + ']'
            try:
                cur.execute(
                    "INSERT INTO embeddings (text_id, comment_id, segment_index, start_pos, end_pos, segment_text, embedding) "
                    "VALUES (%s, NULL, %s, %s, %s, %s, %s)",
                    (tid, seg_idx, start, end, seg, vec_str)
                )
                conn.commit()
            except Exception:
                conn.rollback()
                skipped += 1
        else:  # comment
            cid, seg_idx, start, end, seg = b
            vec_str = '[' + ','.join(f"{v:.6f}" for v in vec) + ']'
            try:
                cur.execute(
                    "INSERT INTO embeddings (text_id, comment_id, segment_index, start_pos, end_pos, segment_text, embedding) "
                    "VALUES (NULL, %s, %s, %s, %s, %s, %s)",
                    (cid, seg_idx, start, end, seg, vec_str)
                )
                conn.commit()
            except Exception:
                conn.rollback()
                skipped += 1

    if skipped > 0:
        print(f"  [WARN] 재시도 중 {skipped}건 건너뜀 (총 {len(batch)}건 중)", flush=True)
    return skipped


def embed_and_save_texts(model, conn, rows):
    """texts 임베딩. rows: [(text_id, content), ...]"""
    cur = conn.cursor()
    total_segments = 0
    total_skipped = 0
    t0 = time.time()

    # 세그먼트 펼치기
    flat = []  # (text_id, segment_index, start, end, segment_text)
    for tid, content in rows:
        for seg_idx, start, end, seg in make_segments(content):
            flat.append((tid, seg_idx, start, end, seg))

    print(f"[texts] 텍스트 {len(rows):,}건 → 세그먼트 {len(flat):,}개", flush=True)

    # 배치 단위 임베딩
    n = len(flat)
    for i in range(0, n, BATCH_SIZE):
        batch = flat[i:i+BATCH_SIZE]
        seg_texts = [b[4] for b in batch]

        vectors = model.encode(
            seg_texts,
            show_progress_bar=False,
            batch_size=BATCH_SIZE,
            convert_to_numpy=True,
        )

        # COPY 방식으로 INSERT (백슬래시·탭·개행 이스케이프)
        buf = io.StringIO()
        for b, vec in zip(batch, vectors):
            tid, seg_idx, start, end, seg = b
            vec_str = '[' + ','.join(f"{v:.6f}" for v in vec) + ']'
            clean = seg.replace('\\', '\\\\').replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
            buf.write(f"{tid}\t\\N\t{seg_idx}\t{start}\t{end}\t{clean}\t{vec_str}\n")

        skipped = copy_batch_with_retry(cur, conn, buf, batch, vectors, kind='text')
        total_skipped += skipped
        total_segments += len(batch) - skipped

        if (i // BATCH_SIZE) % 5 == 0 or i + BATCH_SIZE >= n:
            elapsed = time.time() - t0
            rate = total_segments / elapsed if elapsed > 0 else 0
            eta_h = (n - total_segments) / rate / 3600 if rate > 0 else 0
            print(f"  [texts seg] {total_segments:>9,}/{n:,} ({total_segments/n*100:5.1f}%) "
                  f"| {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 | 남은: {eta_h:.1f}시간", flush=True)

    # 처리된 text_id 일괄 표시
    text_ids = list(set(b[0] for b in flat))
    cur.execute(
        "UPDATE texts SET embeddings_processed = true WHERE text_id = ANY(%s)",
        (text_ids,)
    )
    conn.commit()
    cur.close()

    print(f"[texts] 완료: {len(rows):,}건, 세그먼트 {total_segments:,}개 (건너뜀 {total_skipped:,}건)", flush=True)
    return len(rows), total_segments


def embed_and_save_comments(model, conn, rows):
    """comments 임베딩. rows: [(comment_id, content), ...]"""
    if not rows:
        print("[comments] 처리할 데이터 없음", flush=True)
        return 0, 0

    cur = conn.cursor()
    total_segments = 0
    total_skipped = 0
    t0 = time.time()

    flat = []  # (comment_id, segment_index, start, end, segment_text)
    for cid, content in rows:
        for seg_idx, start, end, seg in make_segments(content):
            flat.append((cid, seg_idx, start, end, seg))

    print(f"[comments] 댓글 {len(rows):,}건 → 세그먼트 {len(flat):,}개", flush=True)

    n = len(flat)
    for i in range(0, n, BATCH_SIZE):
        batch = flat[i:i+BATCH_SIZE]
        seg_texts = [b[4] for b in batch]

        vectors = model.encode(
            seg_texts,
            show_progress_bar=False,
            batch_size=BATCH_SIZE,
            convert_to_numpy=True,
        )

        buf = io.StringIO()
        for b, vec in zip(batch, vectors):
            cid, seg_idx, start, end, seg = b
            vec_str = '[' + ','.join(f"{v:.6f}" for v in vec) + ']'
            clean = seg.replace('\\', '\\\\').replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
            buf.write(f"\\N\t{cid}\t{seg_idx}\t{start}\t{end}\t{clean}\t{vec_str}\n")

        skipped = copy_batch_with_retry(cur, conn, buf, batch, vectors, kind='comment')
        total_skipped += skipped
        total_segments += len(batch) - skipped

        if (i // BATCH_SIZE) % 5 == 0 or i + BATCH_SIZE >= n:
            elapsed = time.time() - t0
            rate = total_segments / elapsed if elapsed > 0 else 0
            eta_h = (n - total_segments) / rate / 3600 if rate > 0 else 0
            print(f"  [comments seg] {total_segments:>9,}/{n:,} ({total_segments/n*100:5.1f}%) "
                  f"| {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 | 남은: {eta_h:.1f}시간", flush=True)

    comment_ids = list(set(b[0] for b in flat))
    cur.execute(
        "UPDATE comments SET embeddings_processed = true WHERE comment_id = ANY(%s)",
        (comment_ids,)
    )
    conn.commit()
    cur.close()

    print(f"[comments] 완료: {len(rows):,}건, 세그먼트 {total_segments:,}개 (건너뜀 {total_skipped:,}건)", flush=True)
    return len(rows), total_segments


def main():
    print(f"=== 임베딩 작업 시작: {datetime.now()} ===", flush=True)
    print(f"GPU 가용: {torch.cuda.is_available()}", flush=True)
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)

    print(f"\n모델 로딩: {MODEL_NAME}", flush=True)
    model = SentenceTransformer(MODEL_NAME, device='cuda' if torch.cuda.is_available() else 'cpu')
    # fp16 (GPU만)
    if torch.cuda.is_available():
        model.half()
    print("모델 로딩 완료\n", flush=True)

    conn = get_conn()

    # 스키마 준비
    ensure_schema(conn)

    # texts 임베딩
    print("\n[1/2] texts 처리 대상 수집 (매체별 샘플링 적용)...", flush=True)
    text_rows = get_target_texts(conn)
    print(f"  합계: {len(text_rows):,}건\n", flush=True)
    t_count, t_segs = embed_and_save_texts(model, conn, text_rows)

    # comments 임베딩
    print("\n[2/2] comments 처리 대상 수집...", flush=True)
    comment_rows = get_target_comments(conn)
    c_count, c_segs = embed_and_save_comments(model, conn, comment_rows)

    # 결과 확인
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM embeddings")
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE text_id IS NOT NULL) AS from_texts,
          COUNT(*) FILTER (WHERE comment_id IS NOT NULL) AS from_comments
        FROM embeddings
    """)
    t_emb, c_emb = cur.fetchone()
    cur.close()
    conn.close()

    print(f"\n=== 완료 ===", flush=True)
    print(f"texts: {t_count:,}건 → 세그먼트 {t_segs:,}", flush=True)
    print(f"comments: {c_count:,}건 → 세그먼트 {c_segs:,}", flush=True)
    print(f"embeddings 총 행수: {total:,} (텍스트 {t_emb:,} + 댓글 {c_emb:,})", flush=True)


if __name__ == '__main__':
    main()
