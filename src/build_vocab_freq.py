"""
morphemes + text_meta → vocab_freq 집계 (월별)

5/24 개정:
- 집계 소스: word_text_map → morphemes (DF → TF)
- count 의미: 토큰 빈도 (한 텍스트 안 같은 단어 반복도 다 셈)
- 일상대화 같은 긴 텍스트의 반복·구어 특징이 빈도에 박힘
- CREATE TABLE IF NOT EXISTS (테이블 없을 때 처음 만들기)
- 날짜 범위 자동 (text_meta MIN/MAX)
- ON CONFLICT 제거 (빈 테이블 시작이라 불필요)
"""
import time
from datetime import date
from db import get_conn


def ensure_table(conn):
    """vocab_freq 테이블·인덱스 없으면 생성."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vocab_freq (
            lemma       varchar(100) NOT NULL,
            pos         varchar(10)  NOT NULL,
            source_id   int          NOT NULL,
            freq_date   date         NOT NULL,
            count       bigint       NOT NULL,
            UNIQUE (lemma, pos, source_id, freq_date)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vocab_freq_lemma_pos ON vocab_freq(lemma, pos)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vocab_freq_date ON vocab_freq(freq_date)")
    conn.commit()
    cur.close()
    print("vocab_freq 테이블·인덱스 확인 완료", flush=True)


def get_date_range(conn):
    """text_meta에서 freq_date MIN/MAX 가져오기."""
    cur = conn.cursor()
    cur.execute("SELECT MIN(freq_date), MAX(freq_date) FROM text_meta")
    mn, mx = cur.fetchone()
    cur.close()
    if mn is None or mx is None:
        raise RuntimeError("text_meta 비어있음 — texts 적재 또는 text_meta 동기화 필요")
    return mn, mx


def iter_months(start_date, end_date):
    """start_date가 속한 월부터 end_date 포함 월까지 (year, month) 순회."""
    y, m = start_date.year, start_date.month
    end_y, end_m = end_date.year, end_date.month
    while (y, m) <= (end_y, end_m):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def build_for_month(conn, year, month):
    cur = conn.cursor()
    start = time.time()

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    start_date = f"{year}-{month:02d}-01"
    end_date = f"{next_year}-{next_month:02d}-01"

    print(f"[{year}-{month:02d}] 집계 시작...", flush=True)

    # morphemes 기반 TF 집계.
    # morphemes는 한 텍스트 안 모든 occurrence가 행으로 있어서
    # GROUP BY 결과의 COUNT(*)가 토큰 빈도(TF).
    cur.execute("""
        INSERT INTO vocab_freq (lemma, pos, source_id, freq_date, count)
        SELECT m.lemma, m.pos, tm.source_id, tm.freq_date, COUNT(*)
        FROM morphemes m
        JOIN text_meta tm ON m.text_id = tm.text_id
        WHERE tm.freq_date >= %s AND tm.freq_date < %s
        GROUP BY m.lemma, m.pos, tm.source_id, tm.freq_date
    """, (start_date, end_date))
    rows = cur.rowcount
    conn.commit()
    cur.close()

    elapsed = time.time() - start
    print(f"[{year}-{month:02d}] 완료: {rows:,}행, {elapsed/60:.1f}분", flush=True)


def main():
    conn = get_conn()

    # 1. 테이블 준비
    ensure_table(conn)

    # 2. 날짜 범위 자동 결정
    mn, mx = get_date_range(conn)
    print(f"text_meta 날짜 범위: {mn} ~ {mx}", flush=True)

    # 3. 월별 루프
    total_start = time.time()
    months = list(iter_months(mn, mx))
    print(f"월 단위 처리 대상: {len(months)}개월", flush=True)
    print("-" * 60, flush=True)

    for year, month in months:
        build_for_month(conn, year, month)

    total_elapsed = time.time() - total_start
    print(f"\n전체 완료! {total_elapsed/60:.0f}분 소요", flush=True)

    # 4. 결과 확인
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM vocab_freq")
    print(f"vocab_freq 총 행수: {cur.fetchone()[0]:,}", flush=True)
    cur.execute("""
        SELECT source_id, COUNT(*) AS rows, SUM(count) AS tokens
        FROM vocab_freq
        GROUP BY source_id
        ORDER BY source_id
    """)
    print("\n매체별 분포:")
    for sid, rows, tokens in cur.fetchall():
        print(f"  source_id={sid}: {rows:,}행, 총 {tokens:,} 토큰")
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
