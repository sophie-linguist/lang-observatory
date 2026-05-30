"""
형태소 분석 → morphemes 저장 (TF 빈도용, texts·comments 통합)

word_text_map과 분리된 별도 작업. 같은 Kiwi 분석·같은 merge_tokens 로직 적용.

특징:
- INSERT 대상: morphemes (한 텍스트 안 모든 occurrence 다 박음, 중복 제거 X)
- 진행 추적: texts.morphemes_processed / comments.morphemes_processed
- surface=lemma 복사, position=NULL (인지의미 분석은 발표 후 작업)
- texts → text_id 박음, comments → comment_id 박음
- 댓글은 한국어 비율 30% 미만이면 skip (5/9 is_korean_dominant 정책)

5/24 동일 합침 전략 적용:
- MM(관형사) 포함
- XR + XSV/XSA 합침 (어근 → 동사·형용사)
- NNG + XSN 합침 (들·네는 블랙리스트로 제외)
"""

import io
import time
from kiwipiepy import Kiwi
from db import get_conn

BATCH_SIZE = 2000
KOREAN_RATIO_THRESHOLD = 0.3  # 댓글 한국어 비율 임계값 (5/9 정책)

KEEP_TAGS = {
    'NNG', 'NNP', 'NNB', 'NR', 'NP',
    'VV', 'VA', 'VCN', 'VCP',
    'MM', 'MAG', 'MAJ',
    'IC',
    'XR',
    'SL',
}

NO_MERGE_XSN = {'들', '네'}


def is_korean_dominant(text):
    """한글 비율 30% 이상이면 True. 영어 위주 댓글 거름."""
    if not text:
        return False
    korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
    total = len(text.strip())
    if total == 0:
        return False
    return (korean_chars / total) >= KOREAN_RATIO_THRESHOLD


def merge_tokens(tokens, text):
    """analyze_morphemes.py와 동일한 합침 로직."""
    results = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        if tok.tag == 'NNG':
            parts = [tok.form]
            end_pos = tok.start + tok.len
            j = i + 1

            while j < n and tokens[j].tag == 'NNG' and tokens[j].start == end_pos:
                parts.append(tokens[j].form)
                end_pos = tokens[j].start + tokens[j].len
                j += 1

            if j < n and tokens[j].start == end_pos:
                if tokens[j].tag.startswith('XSV'):
                    combined = ''.join(parts) + tokens[j].form + '다'
                    results.append((combined, 'VV'))
                    i = j + 1
                    continue
                elif tokens[j].tag.startswith('XSA'):
                    combined = ''.join(parts) + tokens[j].form + '다'
                    results.append((combined, 'VA'))
                    i = j + 1
                    continue
                elif tokens[j].tag == 'XSN' and tokens[j].form not in NO_MERGE_XSN:
                    combined = ''.join(parts) + tokens[j].form
                    results.append((combined, 'NNG'))
                    i = j + 1
                    continue

            combined = ''.join(parts)
            results.append((combined, 'NNG'))
            i = j
            continue

        if tok.tag == 'XR':
            if i + 1 < n and tokens[i + 1].start == tok.start + tok.len:
                nxt = tokens[i + 1]
                if nxt.tag.startswith('XSV'):
                    combined = tok.form + nxt.form + '다'
                    results.append((combined, 'VV'))
                    i += 2
                    continue
                elif nxt.tag.startswith('XSA'):
                    combined = tok.form + nxt.form + '다'
                    results.append((combined, 'VA'))
                    i += 2
                    continue
            results.append((tok.form, 'XR'))
            i += 1
            continue

        if tok.tag in ('VV', 'VA'):
            if (i + 2 < n
                    and tokens[i + 1].tag.startswith('E')
                    and tokens[i + 2].tag == 'VX'):
                vx = tokens[i + 2]
                raw = text[tok.start:vx.start + vx.len]
                combined = raw + '다'
                results.append((combined, tok.tag))
                i += 3
                continue
            else:
                results.append((tok.lemma, tok.tag))
                i += 1
                continue

        if tok.tag in KEEP_TAGS:
            results.append((tok.lemma, tok.tag))

        i += 1

    return results


def process_batch_texts(kiwi, conn, batch):
    """texts 배치 처리. text_id 박음, comment_id NULL."""
    text_ids = [row[0] for row in batch]
    contents = [row[1] for row in batch]

    all_tokens = kiwi.tokenize(contents)

    buf = io.StringIO()
    for idx, tokens in enumerate(all_tokens):
        tid = text_ids[idx]
        merged = merge_tokens(tokens, contents[idx])
        for lemma, pos in merged:
            if not lemma or len(lemma) > 100 or len(pos) > 10:
                continue
            clean = lemma.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
            buf.write(f"{tid}\t\\N\t{clean}\t{clean}\t{pos}\t\\N\n")

    cur = conn.cursor()
    if buf.tell() > 0:
        buf.seek(0)
        cur.copy_from(
            buf, 'morphemes',
            columns=('text_id', 'comment_id', 'surface', 'lemma', 'pos', 'position')
        )
    cur.execute(
        "UPDATE texts SET morphemes_processed = true WHERE text_id = ANY(%s)",
        (text_ids,)
    )
    conn.commit()
    cur.close()


def process_batch_comments(kiwi, conn, batch):
    """comments 배치 처리. comment_id 박음, text_id NULL. 영어 댓글 skip."""
    filtered = [(cid, content) for cid, content in batch if is_korean_dominant(content)]
    skipped_ids = [cid for cid, content in batch if not is_korean_dominant(content)]
    all_ids = [row[0] for row in batch]

    if filtered:
        comment_ids = [row[0] for row in filtered]
        contents = [row[1] for row in filtered]

        all_tokens = kiwi.tokenize(contents)

        buf = io.StringIO()
        for idx, tokens in enumerate(all_tokens):
            cid = comment_ids[idx]
            merged = merge_tokens(tokens, contents[idx])
            for lemma, pos in merged:
                if not lemma or len(lemma) > 100 or len(pos) > 10:
                    continue
                clean = lemma.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
                buf.write(f"\\N\t{cid}\t{clean}\t{clean}\t{pos}\t\\N\n")

        cur = conn.cursor()
        if buf.tell() > 0:
            buf.seek(0)
            cur.copy_from(
                buf, 'morphemes',
                columns=('text_id', 'comment_id', 'surface', 'lemma', 'pos', 'position')
            )
        cur.close()

    cur = conn.cursor()
    cur.execute(
        "UPDATE comments SET morphemes_processed = true WHERE comment_id = ANY(%s)",
        (all_ids,)
    )
    conn.commit()
    cur.close()

    return len(skipped_ids)


def run_texts(kiwi, conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM texts WHERE morphemes_processed = false")
    total = cur.fetchone()[0]
    cur.close()

    if total == 0:
        print("[texts] 처리할 데이터 없음")
        return 0

    print(f"[texts] 처리 대상: {total:,}건")
    print("-" * 60)

    processed = 0
    last_id = 0
    start_time = time.time()

    while True:
        cur = conn.cursor()
        cur.execute("""
            SELECT text_id, content FROM texts
            WHERE text_id > %s AND morphemes_processed = false
            ORDER BY text_id
            LIMIT %s
        """, (last_id, BATCH_SIZE))
        batch = cur.fetchall()
        cur.close()

        if not batch:
            break

        last_id = batch[-1][0]

        try:
            process_batch_texts(kiwi, conn, batch)
        except Exception as e:
            print(f"\n[ERROR texts] text_id {batch[0][0]}~{batch[-1][0]}: {e}")
            conn.rollback()
            continue

        processed += len(batch)

        if (processed // BATCH_SIZE) % 5 == 0 or processed >= total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta_h = (total - processed) / rate / 3600 if rate > 0 else 0
            print(f"  [texts] {processed:>10,}/{total:,} ({processed/total*100:5.1f}%) "
                  f"| {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 "
                  f"| 남은: {eta_h:.1f}시간")

    elapsed = time.time() - start_time
    print(f"[texts] 완료: {processed:,}건, {elapsed/60:.1f}분")
    return processed


def run_comments(kiwi, conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM comments WHERE morphemes_processed = false")
    total = cur.fetchone()[0]
    cur.close()

    if total == 0:
        print("[comments] 처리할 데이터 없음")
        return 0

    print(f"[comments] 처리 대상: {total:,}건")
    print("-" * 60)

    processed = 0
    skipped = 0
    last_id = 0
    start_time = time.time()

    while True:
        cur = conn.cursor()
        cur.execute("""
            SELECT comment_id, content FROM comments
            WHERE comment_id > %s AND morphemes_processed = false
            ORDER BY comment_id
            LIMIT %s
        """, (last_id, BATCH_SIZE))
        batch = cur.fetchall()
        cur.close()

        if not batch:
            break

        last_id = batch[-1][0]

        try:
            skipped_this = process_batch_comments(kiwi, conn, batch)
            skipped += skipped_this
        except Exception as e:
            print(f"\n[ERROR comments] comment_id {batch[0][0]}~{batch[-1][0]}: {e}")
            conn.rollback()
            continue

        processed += len(batch)

        if (processed // BATCH_SIZE) % 5 == 0 or processed >= total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta_h = (total - processed) / rate / 3600 if rate > 0 else 0
            print(f"  [comments] {processed:>10,}/{total:,} ({processed/total*100:5.1f}%) "
                  f"| skip {skipped:,} | {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 "
                  f"| 남은: {eta_h:.1f}시간")

    elapsed = time.time() - start_time
    print(f"[comments] 완료: {processed:,}건 (영어 skip {skipped:,}), {elapsed/60:.1f}분")
    return processed


def main():
    print("Kiwi 모델 로딩 중...")
    kiwi = Kiwi()
    print("Kiwi 로딩 완료\n")

    conn = get_conn()

    total_start = time.time()
    n_texts = run_texts(kiwi, conn)
    n_comments = run_comments(kiwi, conn)

    elapsed = time.time() - total_start
    print("=" * 60)
    print(f"전체 완료! texts {n_texts:,} + comments {n_comments:,}, {elapsed/60:.1f}분")

    print("\n인덱스 생성 중...")
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_morphemes_lemma_pos ON morphemes(lemma, pos)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_morphemes_text_id ON morphemes(text_id) WHERE text_id IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_morphemes_comment_id ON morphemes(comment_id) WHERE comment_id IS NOT NULL")
    conn.commit()
    cur.close()
    print("인덱스 생성 완료")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM morphemes")
    print(f"\nmorphemes 총 행수: {cur.fetchone()[0]:,}")
    cur.execute("""
        SELECT 
          COUNT(*) FILTER (WHERE text_id IS NOT NULL) AS from_texts,
          COUNT(*) FILTER (WHERE comment_id IS NOT NULL) AS from_comments
        FROM morphemes
    """)
    t_cnt, c_cnt = cur.fetchone()
    print(f"  texts에서: {t_cnt:,}")
    print(f"  comments에서: {c_cnt:,}")
    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
