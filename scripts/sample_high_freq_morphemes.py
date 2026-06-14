"""
모두의말뭉치 고빈도 단어 morphemes 샘플링

목적:
- morphemes 테이블에서 모두의말뭉치(source_id 5,6)의 고빈도 단어만 샘플링
- 일별 10개씩만 유지, 나머지 삭제
- 네이버 뉴스, 유튜브 댓글은 그대로 유지 (실시간 수집, refresh 필요)
- 저빈도 단어는 완전 보존 (신어 발견에 필수)

예상 효과:
- 약 60GB 절약
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from db import get_conn


FREQ_THRESHOLD = 10000  # 이 빈도 이상 단어를 샘플링
DAILY_SAMPLE_SIZE = 10  # 일별 유지할 샘플 수


def main():
    print(f"{'='*80}")
    print(f"고빈도 단어 morphemes 샘플링")
    print(f"임계값: {FREQ_THRESHOLD:,}회 이상")
    print(f"일별 유지: {DAILY_SAMPLE_SIZE}개")
    print(f"{'='*80}\n")

    conn = get_conn()
    cur = conn.cursor()

    # 1. 현재 morphemes 통계
    print("1. 현재 morphemes 테이블 통계...")
    cur.execute("SELECT COUNT(*) FROM morphemes")
    total_before = cur.fetchone()[0]
    print(f"   총 레코드 수: {total_before:,}\n")

    # 2. 고빈도 단어 식별
    print(f"2. 고빈도 단어 식별 (빈도 ≥ {FREQ_THRESHOLD:,}회)...")
    cur.execute("""
        CREATE TEMP TABLE high_freq_words AS
        SELECT lemma, pos, COUNT(*) as total_freq
        FROM morphemes
        GROUP BY lemma, pos
        HAVING COUNT(*) >= %s
    """, (FREQ_THRESHOLD,))

    cur.execute("SELECT COUNT(*) FROM high_freq_words")
    high_freq_count = cur.fetchone()[0]
    print(f"   고빈도 단어: {high_freq_count:,}개")

    if high_freq_count == 0:
        print("\n   고빈도 단어가 없습니다. 종료합니다.")
        cur.close()
        conn.close()
        return

    # 고빈도 단어 예시
    cur.execute("""
        SELECT lemma, pos, total_freq
        FROM high_freq_words
        ORDER BY total_freq DESC
        LIMIT 10
    """)
    print("\n   상위 10개:")
    for lemma, pos, freq in cur.fetchall():
        print(f"     - {lemma:15} ({pos}) {freq:>12,}회")

    # 3. 삭제할 레코드 수 계산
    print("\n3. 삭제 대상 레코드 계산 중 (모두의말뭉치만)...")
    cur.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT m.morpheme_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY
                           m.lemma,
                           m.pos,
                           DATE(t.published_at)
                       ORDER BY RANDOM()
                   ) as daily_rank
            FROM morphemes m
            INNER JOIN high_freq_words h ON m.lemma = h.lemma AND m.pos = h.pos
            INNER JOIN texts t ON m.text_id = t.text_id
            WHERE t.source_id IN (5, 6)  -- 모두의말뭉치만
        ) ranked
        WHERE daily_rank > %s
    """, (DAILY_SAMPLE_SIZE,))

    delete_count = cur.fetchone()[0]
    print(f"   삭제 대상: {delete_count:,}개")
    print(f"   유지 예상: {total_before - delete_count:,}개")
    print(f"   삭제 비율: {delete_count/total_before*100:.1f}%\n")

    # 4. 사용자 확인 (자동 진행)
    print(f"   자동으로 진행합니다...")
    # response = input(f"   계속 진행하시겠습니까? (yes/no): ").strip().lower()
    # if response != 'yes':
    #     print("\n   취소되었습니다.")
    #     cur.close()
    #     conn.close()
    #     return

    # 5. 샘플링 실행
    print("\n4. 모두의말뭉치 고빈도 단어 샘플링 실행 중...")
    print("   (시간이 오래 걸릴 수 있습니다. 약 30분~1시간 예상)\n")

    start_time = datetime.now()

    cur.execute("""
        DELETE FROM morphemes
        WHERE morpheme_id IN (
            SELECT morpheme_id
            FROM (
                SELECT m.morpheme_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY
                               m.lemma,
                               m.pos,
                               DATE(t.published_at)
                           ORDER BY RANDOM()
                       ) as daily_rank
                FROM morphemes m
                INNER JOIN high_freq_words h ON m.lemma = h.lemma AND m.pos = h.pos
                INNER JOIN texts t ON m.text_id = t.text_id
                WHERE t.source_id IN (5, 6)  -- 모두의말뭉치만
            ) ranked
            WHERE daily_rank > %s
        )
    """, (DAILY_SAMPLE_SIZE,))

    deleted = cur.rowcount
    conn.commit()

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"   ✓ 삭제 완료: {deleted:,}개 ({elapsed:.1f}초)\n")

    # 6. VACUUM FULL로 공간 회수
    print("5. VACUUM FULL 실행 중 (공간 회수)...")
    print("   (시간이 오래 걸릴 수 있습니다. 약 30분~1시간 예상)\n")

    start_time = datetime.now()

    # PostgreSQL에서 VACUUM FULL은 자동 커밋이므로 별도 연결 필요
    conn.set_isolation_level(0)  # autocommit
    cur.execute("VACUUM FULL morphemes")
    conn.set_isolation_level(1)  # 원래대로

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"   ✓ VACUUM 완료 ({elapsed/60:.1f}분)\n")

    # 7. 결과 확인
    print("6. 최종 결과:")
    cur.execute("SELECT COUNT(*) FROM morphemes")
    total_after = cur.fetchone()[0]

    cur.execute("""
        SELECT pg_size_pretty(pg_total_relation_size('morphemes'))
    """)
    size_after = cur.fetchone()[0]

    print(f"   삭제 전: {total_before:,}개")
    print(f"   삭제 후: {total_after:,}개")
    print(f"   삭제량: {total_before - total_after:,}개 ({(total_before-total_after)/total_before*100:.1f}%)")
    print(f"   현재 테이블 크기: {size_after}")
    print(f"\n{'='*80}")
    print("완료!")
    print(f"{'='*80}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
