"""댓글 문장 임베딩 → pgvector 저장 파이프라인 (embed_texts.py의 댓글 버전)"""
import os, sys, time
import argparse
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn

MODEL_NAME = "BAAI/bge-m3"
BATCH_SIZE = 64
EMBEDDING_TYPE = "sentence"


def get_unembedded_comments(cur, days_limit=None):
    """임베딩 안 된 댓글 가져오기.
    
    days_limit=None (default): 전체 댓글 (첫 실행용)
    days_limit=N: 최근 N일치만 (매일 cron용)
    """
    if days_limit is None:
        cur.execute("""
            SELECT c.comment_id, c.content
            FROM comments c
            WHERE c.content IS NOT NULL
              AND c.content != ''
              AND NOT EXISTS (
                  SELECT 1 FROM embeddings e
                  WHERE e.comment_id = c.comment_id
                    AND e.embedding_type = %s
              )
            ORDER BY c.comment_id DESC
        """, (EMBEDDING_TYPE,))
    else:
        cur.execute("""
            SELECT c.comment_id, c.content
            FROM comments c
            WHERE c.content IS NOT NULL
              AND c.content != ''
              AND c.published_at > NOW() - INTERVAL '%s days'
              AND NOT EXISTS (
                  SELECT 1 FROM embeddings e
                  WHERE e.comment_id = c.comment_id
                    AND e.embedding_type = %s
              )
            ORDER BY c.comment_id DESC
        """, (days_limit, EMBEDDING_TYPE))
    return cur.fetchall()


def save_embeddings(cur, comment_ids, vectors):
    """벡터 배열 → embeddings 테이블 (comment_id 컬럼 사용)"""
    for cid, vec in zip(comment_ids, vectors):
        cur.execute("""
            INSERT INTO embeddings (comment_id, embedding_type, embedding)
            VALUES (%s, %s, %s)
        """, (cid, EMBEDDING_TYPE, vec.tolist()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=None,
                        help='최근 N일치만 처리. 안 주면 전체.')
    args = parser.parse_args()

    print(f"모델 로딩: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print("모델 로딩 완료")

    conn = get_conn()
    cur = conn.cursor()

    rows = get_unembedded_comments(cur, days_limit=args.days)
    total = len(rows)
    print(f"임베딩 대상: {total}건 (days_limit={args.days})")

    if total == 0:
        print("처리할 데이터 없음")
        cur.close(); conn.close()
        return

    t0 = time.time()
    processed = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        comment_ids = [r[0] for r in batch]
        contents = [r[1][:512] for r in batch]
        vectors = model.encode(contents, show_progress_bar=False)
        save_embeddings(cur, comment_ids, vectors)
        conn.commit()
        processed += len(batch)
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        eta_h = (total - processed) / rate / 3600 if rate > 0 else 0
        if processed % (BATCH_SIZE * 10) == 0 or processed >= total:
            print(f"  {processed}/{total} ({rate:.1f}건/초, ETA {eta_h:.1f}시간)")

    elapsed = time.time() - t0
    print(f"\n[완료] {processed}건, {elapsed:.1f}초 소요 ({processed/elapsed:.1f}건/초)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
