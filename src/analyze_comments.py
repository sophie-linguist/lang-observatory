#!/usr/bin/env python3
"""
댓글 형태소 분석 → word_comment_map 저장
analyze_morphemes.py의 댓글 버전.
"""

import io
import time
from kiwipiepy import Kiwi
from db import get_conn

BATCH_SIZE = 2000

KEEP_TAGS = {
    'NNG', 'NNP', 'NNB', 'NR', 'NP',
    'VV', 'VA', 'VCN', 'VCP',
    'MAG', 'MAJ',
    'IC',
    'XR',
    'SL',
}


def is_korean_dominant(text, threshold=0.3):
    """텍스트가 한국어 비율 충분한지 판단. 한글 글자 비율 threshold 미만이면 영어 댓글로 판단."""
    if not text or not text.strip():
        return False
    
    korean_chars = sum(1 for c in text if '가' <= c <= '힣')
    total_chars = sum(1 for c in text if c.isalpha() or '가' <= c <= '힣')
    
    if total_chars == 0:
        return False
    
    return korean_chars / total_chars >= threshold

def merge_tokens(tokens, text):
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

            combined = ''.join(parts)
            results.append((combined, 'NNG'))
            i = j
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


def process_batch(kiwi, conn, batch):
    # 영어 댓글은 빼되, is_processed는 true로 마킹 (다시 처리 안 하도록)
    korean_batch = [(cid, content) for cid, content in batch if is_korean_dominant(content)]
    skipped_ids = [cid for cid, content in batch if not is_korean_dominant(content)]
    
    if korean_batch:
        comment_ids = [row[0] for row in korean_batch]
        contents = [row[1] for row in korean_batch]
        all_tokens = kiwi.tokenize(contents)
    else:
        comment_ids = []
        contents = []
        all_tokens = []

    buf = io.StringIO()
    seen = set()
    for idx, tokens in enumerate(all_tokens):
        comment_id = comment_ids[idx]
        merged = merge_tokens(tokens, contents[idx])
        for lemma, pos in merged:
            if not lemma or len(lemma) > 100 or len(pos) > 10:
                continue
            key = (lemma, pos, comment_id)
            if key not in seen:
                seen.add(key)
                clean = lemma.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
                buf.write(f"{clean}\t{pos}\t{comment_id}\n")

    cur = conn.cursor()

    if buf.tell() > 0:
        buf.seek(0)
        cur.copy_from(buf, 'word_comment_map', columns=('lemma', 'pos', 'comment_id'))
    
    all_processed_ids = comment_ids + skipped_ids
    cur.execute("UPDATE comments SET is_processed = true WHERE comment_id = ANY(%s)",
                (all_processed_ids,))
    conn.commit()
    cur.close()


def main():
    print("Kiwi 모델 로딩 중...")
    kiwi = Kiwi()
    print("Kiwi 로딩 완료")

    conn = get_conn()

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM comments WHERE is_processed = false")
    total = cur.fetchone()[0]
    cur.close()

    if total == 0:
        print("처리할 데이터가 없습니다")
        conn.close()
        return

    print(f"처리 대상: {total:,}건 (BATCH_SIZE={BATCH_SIZE})")
    print("-" * 60)

    processed = 0
    last_id = 0
    start_time = time.time()

    while True:
        cur = conn.cursor()
        cur.execute("""
            SELECT comment_id, content FROM comments
            WHERE comment_id > %s AND is_processed = false
            ORDER BY comment_id
            LIMIT %s
        """, (last_id, BATCH_SIZE))
        batch = cur.fetchall()
        cur.close()

        if not batch:
            break

        last_id = batch[-1][0]

        try:
            process_batch(kiwi, conn, batch)
        except Exception as e:
            print(f"\n[ERROR] comment_id {batch[0][0]}~{batch[-1][0]}: {e}")
            conn.rollback()
            last_id = batch[-1][0]
            continue

        processed += len(batch)

        if (processed // BATCH_SIZE) % 5 == 0 or processed >= total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta_min = (total - processed) / rate / 60 if rate > 0 else 0
            print(f"  {processed:>10,}/{total:,} ({processed/total*100:5.1f}%) "
                  f"| {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 "
                  f"| 남은 시간: {eta_min:.1f}분")

    elapsed = time.time() - start_time
    print("=" * 60)
    print(f"적재 완료! {processed:,}건, {elapsed/60:.1f}분 소요")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM word_comment_map")
    map_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"word_comment_map: {map_count:,}행")


if __name__ == '__main__':
    main()
