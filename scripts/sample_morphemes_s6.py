"""
모두의말뭉치 신문(source 6) morphemes 샘플링 - INSERT 방식

목적:
- source 6 (모두의말뭉치 신문, 전체 morphemes의 98%)만 일별/단어별 10개 예시만 유지
- 나머지 전부 보존: source 5(구어), 3(네이버), 4(유튜브영상), 7(유튜브댓글)
- vocab_freq는 이미 집계 완료 → morphemes는 용례 보관용

방식 (INSERT 기반, 인덱스 갱신 비용 제거):
- 인덱스 없는 새 테이블 morphemes_new에 "남길 것만" INSERT
- 비-신문(non-6)은 전량 복사
- 신문(6)은 날짜별로 (lemma,pos) 10개씩만 INSERT (날짜별 커밋 → 재개 가능)
- 완료 후 인덱스 일괄 생성 → 테이블 교체

테스트 검증:
- 하루치 DELETE = 5분 6초 (인덱스 갱신)
- 하루치 INSERT = 2.3초 (135배 빠름)

주의:
- 원본은 morphemes_old로 보존. 검증 후 수동 삭제 필요.
"""

import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from db import get_conn

DAILY_SAMPLE_SIZE = 10
CORPUS_SOURCE = 6  # 모두의말뭉치 신문만


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    log("=" * 70)
    log(f"신문 코퍼스(source {CORPUS_SOURCE}) morphemes 샘플링 시작")
    log(f"일별/단어별 유지: {DAILY_SAMPLE_SIZE}개")
    log("=" * 70)

    conn = get_conn()
    cur = conn.cursor()

    # ---------- A. 준비 ----------
    log("A. 준비 단계")

    # text_meta 인덱스 (배치 조회 가속)
    log("  - text_meta 인덱스 확인/생성...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_text_meta_source_date
        ON text_meta(source_id, freq_date)
    """)
    conn.commit()

    # 진행 기록 테이블 (재개용)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _s6_sampling_progress (
            freq_date date PRIMARY KEY,
            done_at timestamp DEFAULT now()
        )
    """)
    conn.commit()

    # morphemes_new 생성 여부 확인
    cur.execute("SELECT to_regclass('public.morphemes_new')")
    exists = cur.fetchone()[0] is not None

    if not exists:
        log("  - morphemes_new 생성 (인덱스 없음)...")
        cur.execute("""
            CREATE TABLE morphemes_new (
                LIKE morphemes INCLUDING DEFAULTS INCLUDING CONSTRAINTS
            )
        """)
        conn.commit()

        # ---------- B. 비-신문(non-6) 전량 복사 ----------
        log("B. 비-신문 데이터 전량 복사")

        # B1. 댓글 기반 (source 7) - 부분 인덱스 활용
        log("  - B1. 댓글 기반 morphemes 복사 중...")
        t0 = time.time()
        cur.execute("""
            INSERT INTO morphemes_new
            SELECT * FROM morphemes WHERE comment_id IS NOT NULL
        """)
        log(f"    ✓ {cur.rowcount:,}개 ({time.time()-t0:.1f}초)")
        conn.commit()

        # B2. 텍스트 기반 비-신문 (source 3,4,5)
        log("  - B2. source 3/4/5 텍스트 기반 morphemes 복사 중...")
        t0 = time.time()
        cur.execute("""
            INSERT INTO morphemes_new
            SELECT m.* FROM morphemes m
            WHERE m.text_id IN (
                SELECT text_id FROM text_meta WHERE source_id IN (3, 4, 5)
            )
        """)
        log(f"    ✓ {cur.rowcount:,}개 ({time.time()-t0:.1f}초)")
        conn.commit()
    else:
        log("  - morphemes_new 이미 존재 → 재개 모드")

    # ---------- C. 신문(source 6) 날짜별 샘플링 ----------
    log("C. 신문(source 6) 날짜별 샘플링 INSERT")

    # 처리할 날짜 목록 (아직 안 한 것만)
    cur.execute("""
        SELECT DISTINCT tm.freq_date
        FROM text_meta tm
        WHERE tm.source_id = %s
          AND tm.freq_date NOT IN (SELECT freq_date FROM _s6_sampling_progress)
        ORDER BY tm.freq_date
    """, (CORPUS_SOURCE,))
    dates = [r[0] for r in cur.fetchall()]
    total_dates = len(dates)
    log(f"  - 처리할 날짜: {total_dates:,}일")

    if total_dates == 0:
        log("  - 모든 날짜 처리 완료됨 (재개)")
    else:
        start = time.time()
        inserted_total = 0
        for i, d in enumerate(dates, 1):
            cur.execute("""
                INSERT INTO morphemes_new
                    (morpheme_id, text_id, comment_id, surface, lemma, pos, "position")
                SELECT morpheme_id, text_id, comment_id, surface, lemma, pos, "position"
                FROM (
                    SELECT m.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY m.lemma, m.pos
                               ORDER BY RANDOM()
                           ) AS rk
                    FROM morphemes m
                    WHERE m.text_id IN (
                        SELECT text_id FROM text_meta
                        WHERE source_id = %s AND freq_date = %s
                    )
                ) s
                WHERE rk <= %s
            """, (CORPUS_SOURCE, d, DAILY_SAMPLE_SIZE))
            inserted_total += cur.rowcount

            cur.execute(
                "INSERT INTO _s6_sampling_progress(freq_date) VALUES (%s) "
                "ON CONFLICT DO NOTHING", (d,))
            conn.commit()

            if i % 50 == 0 or i == total_dates:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total_dates - i) / rate / 60
                log(f"  - {i:,}/{total_dates:,} ({i/total_dates*100:.1f}%) | "
                    f"누적 INSERT {inserted_total:,} | "
                    f"{rate:.1f}일/초 | 남은 시간 ~{eta:.1f}분")

        log(f"  ✓ 신문 샘플링 완료: {inserted_total:,}개 INSERT "
            f"({(time.time()-start)/60:.1f}분)")

    # ---------- D. 인덱스 일괄 생성 ----------
    log("D. 인덱스 생성 (3.1억 행, ~30-40분 예상)")
    conn.set_isolation_level(0)  # autocommit (인덱스 생성)

    for name, ddl in [
        ("text_id", "CREATE INDEX IF NOT EXISTS idx_morphemes_new_text_id "
                     "ON morphemes_new(text_id) WHERE text_id IS NOT NULL"),
        ("comment_id", "CREATE INDEX IF NOT EXISTS idx_morphemes_new_comment_id "
                       "ON morphemes_new(comment_id) WHERE comment_id IS NOT NULL"),
        ("lemma_pos", "CREATE INDEX IF NOT EXISTS idx_morphemes_new_lemma_pos "
                      "ON morphemes_new(lemma, pos)"),
    ]:
        t0 = time.time()
        log(f"  - {name} 인덱스 생성 중...")
        cur.execute(ddl)
        log(f"    ✓ ({(time.time()-t0)/60:.1f}분)")

    conn.set_isolation_level(1)

    # ---------- E. 결과 요약 (교체는 수동 확인 후) ----------
    cur.execute("SELECT COUNT(*) FROM morphemes_new")
    new_count = cur.fetchone()[0]
    cur.execute("SELECT pg_size_pretty(pg_total_relation_size('morphemes_new'))")
    new_size = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM morphemes")
    old_count = cur.fetchone()[0]

    log("=" * 70)
    log("샘플링 완료 (교체 전)")
    log(f"  원본 morphemes:     {old_count:,}개")
    log(f"  신규 morphemes_new: {new_count:,}개 ({new_size})")
    log(f"  감소: {old_count-new_count:,}개 ({(old_count-new_count)/old_count*100:.1f}%)")
    log("=" * 70)
    log("다음 단계 (수동 확인 후 실행):")
    log("  BEGIN;")
    log("  ALTER TABLE morphemes RENAME TO morphemes_old;")
    log("  ALTER TABLE morphemes_new RENAME TO morphemes;")
    log("  COMMIT;")
    log("  -- 검증 후: DROP TABLE morphemes_old; (89GB 회수)")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
