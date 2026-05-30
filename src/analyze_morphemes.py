"""
형태소 분석 → word_text_map 저장 (고속 버전)
COPY 방식으로 벌크 로드, 인덱스는 완료 후 생성

5/24 개정:
- KEEP_TAGS에 MM(관형사) 추가
- XR + XSV/XSA 합침 로직 추가 (어근 → 동사·형용사)
- NNG + XSN 합침 로직 추가 (들·네는 블랙리스트로 제외)
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

# XSN 합침 블랙리스트: 굴절·복수 접미사. 의미 단위 만들지 않음
NO_MERGE_XSN = {'들', '네'}


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

            # 연속된 NNG 토큰 끌어모으기
            while j < n and tokens[j].tag == 'NNG' and tokens[j].start == end_pos:
                parts.append(tokens[j].form)
                end_pos = tokens[j].start + tokens[j].len
                j += 1

            # 다음 토큰 분기 (위치가 딱 붙어있을 때만)
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
                    # 명사파생접미사 합쳐서 NNG로 박고 멈춤
                    combined = ''.join(parts) + tokens[j].form
                    results.append((combined, 'NNG'))
                    i = j + 1
                    continue

            # 그냥 NNG 연쇄로 남기기
            combined = ''.join(parts)
            results.append((combined, 'NNG'))
            i = j
            continue

        # XR + XSV/XSA → VV/VA
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
            # 합칠 거 없으면 XR 단독
            results.append((tok.form, 'XR'))
            i += 1
            continue

        # VV/VA + E + VX 합치기 (기존 로직 유지)
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
    text_ids = [row[0] for row in batch]
    contents = [row[1] for row in batch]

    all_tokens = kiwi.tokenize(contents)

    # 중복 제거 후 COPY용 데이터 생성
    buf = io.StringIO()
    seen = set()
    for idx, tokens in enumerate(all_tokens):
        text_id = text_ids[idx]
        merged = merge_tokens(tokens, contents[idx])
        for lemma, pos in merged:
            if not lemma or len(lemma) > 100 or len(pos) > 10:
                continue
            key = (lemma, pos, text_id)
            if key not in seen:
                seen.add(key)
                # 탭이나 개행 포함된 lemma 방어
                clean = lemma.replace('\t', ' ').replace('\n', ' ')
                buf.write(f"{clean}\t{pos}\t{text_id}\n")

    cur = conn.cursor()

    if buf.tell() > 0:
        buf.seek(0)
        cur.copy_from(buf, 'word_text_map', columns=('lemma', 'pos', 'text_id'))

    cur.execute("UPDATE texts SET is_processed = true WHERE text_id = ANY(%s)",
                (text_ids,))
    conn.commit()
    cur.close()


def main():
    print("Kiwi 모델 로딩 중...")
    kiwi = Kiwi()
    print("Kiwi 로딩 완료")

    conn = get_conn()

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM texts WHERE is_processed = false")
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
            SELECT text_id, content FROM texts
            WHERE text_id > %s AND is_processed = false
            ORDER BY text_id
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
            print(f"\n[ERROR] text_id {batch[0][0]}~{batch[-1][0]}: {e}")
            last_id = batch[-1][0]
            continue

        processed += len(batch)

        if (processed // BATCH_SIZE) % 5 == 0 or processed >= total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta_h = (total - processed) / rate / 3600 if rate > 0 else 0
            print(f"  {processed:>10,}/{total:,} ({processed/total*100:5.1f}%) "
                  f"| {rate:,.0f}건/초 | 경과: {elapsed/60:.0f}분 "
                  f"| 남은 시간: {eta_h:.1f}시간")

    elapsed = time.time() - start_time
    print("=" * 60)
    print(f"적재 완료! {processed:,}건, {elapsed/60:.1f}분 소요")

    # 인덱스 재생성
    print("인덱스 생성 중...")
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_word_text_map_lemma ON word_text_map(lemma)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_word_text_map_text_id ON word_text_map(text_id)")
    conn.commit()
    cur.close()
    print("인덱스 생성 완료")

    # 결과 확인
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM word_text_map")
    map_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"word_text_map: {map_count:,}행")


if __name__ == '__main__':
    main()
