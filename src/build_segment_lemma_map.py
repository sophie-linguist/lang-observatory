"""
세그먼트별 형태소 매핑 (segment_lemma_map 생성)

embeddings.segment_text를 Kiwi로 분석 → (embedding_id, lemma, pos) 저장.
analyze_morphemes_tf.py와 동일한 merge_tokens 로직 적용.

용도: 클러스터링 시 "이 lemma가 등장한 세그먼트(embedding_id)"를 빠르게 조회.
"""

import io
import time
from kiwipiepy import Kiwi
from db import get_conn

BATCH_SIZE = 2000

KEEP_TAGS = {
    'NNG', 'NNP', 'NNB', 'NR', 'NP',
    'VV', 'VA', 'VCN', 'VCP',
    'MM', 'MAG', 'MAJ',
    'IC',
    'XR',
    'SL',
}

NO_MERGE_XSN = {'들', '네'}


def merge_tokens(tokens, text):
    """analyze_morphemes_tf.py와 동일한 합침 로직."""
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


def main():
    print("Kiwi 모델 로딩 중...")
    kiwi = Kiwi()
    print("Kiwi 로딩 완료\n")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM embeddings")
    total = cur.fetchone()[0]
    print(f"세그먼트 총 {total:,}건")

    processed = 0
    last_id = 0
    total_errors = 0
    start_time = time.time()

    while True:
        cur.execute("""
            SELECT embedding_id, segment_text
            FROM embeddings
            WHERE embedding_id > %s
            ORDER BY embedding_id
            LIMIT %s
        """, (last_id, BATCH_SIZE))
        batch = cur.fetchall()

        if not batch:
            break

        last_id = batch[-1][0]

        embedding_ids = [row[0] for row in batch]
        texts = [row[1] for row in batch]

        all_tokens = kiwi.tokenize(texts)

        buf = io.StringIO()
        errors = []
        for idx, tokens in enumerate(all_tokens):
            eid = embedding_ids[idx]
            try:
                merged = merge_tokens(tokens, texts[idx])

                seen = set()
                for lemma, pos in merged:
                    if not lemma or len(lemma) > 100 or len(pos) > 10:
                        continue
                    key = (lemma, pos)
                    if key in seen:
                        continue
                    seen.add(key)
                    clean = lemma.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
                    buf.write(f"{eid}\t{clean}\t{pos}\n")
            except Exception as e:
                # 개별 segment 에러는 로그만 남기고 계속 진행
                errors.append((eid, str(e)))
                continue

        if buf.tell() > 0:
            buf.seek(0)
            cur.copy_from(
                buf, 'segment_lemma_map',
                columns=('embedding_id', 'lemma', 'pos')
            )
            conn.commit()

        # 에러 로그
        if errors:
            total_errors += len(errors)
            for eid, err in errors:
                print(f"  ⚠️  embedding_id={eid}: {err}")

        processed += len(batch)

        if (processed // BATCH_SIZE) % 10 == 0 or processed >= total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta_h = (total - processed) / rate / 3600 if rate > 0 else 0
            print(f"  {processed:>10,}/{total:,} ({processed/total*100:5.1f}%) "
                  f"| {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 "
                  f"| 남은: {eta_h:.1f}시간")

    elapsed = time.time() - start_time
    print(f"\n완료: {processed:,}건, {elapsed/60:.1f}분")
    if total_errors > 0:
        print(f"⚠️  에러 발생: {total_errors:,}건 (스킵됨)")
        print(f"✅ 성공: {processed - total_errors:,}건 ({(processed-total_errors)/processed*100:.1f}%)")

    print("\n인덱스 생성 중...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seg_lemma_map_lemma_pos ON segment_lemma_map(lemma, pos)")
    conn.commit()
    print("인덱스 생성 완료")

    cur.execute("SELECT COUNT(*) FROM segment_lemma_map")
    print(f"segment_lemma_map 총 행수: {cur.fetchone()[0]:,}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
