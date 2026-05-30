"""
vocab_freq 일일 증분 갱신 (TF 버전)

5/24 개정:
- 집계 소스: word_text_map → morphemes (DF → TF)
- 댓글 [4/4] 단계: word_comment_map → morphemes (comment_id 기준)
- 본 시스템은 댓글까지 포함이 완성형 (5/9 결정 유지)

동작:
- 어제~오늘 처리된 텍스트의 freq_date 범위 데이터를 DELETE 후 재집계
- 신문 등 texts: text_meta JOIN으로 source_id·freq_date 가져옴
- 유튜브 댓글: source_id=7 고정, comments.published_at::date를 freq_date로
- vocab_lemma_summary 통째 재생성
- 신어 후보 갱신
"""
import sys, os, time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import get_conn


def refresh_recent_days(conn, days=7):
    """최근 N일치 freq_date의 vocab_freq를 다시 집계.

    1. 최근 N일 freq_date 범위 결정
    2. 해당 범위의 vocab_freq 데이터 DELETE (texts·comments 양쪽)
    3. text_meta 동기화 (새 텍스트 메타 추가분 반영)
    4. morphemes (text_id 기준) → vocab_freq 재집계
    5. morphemes (comment_id 기준) → vocab_freq 재집계 (source_id=7)
    """
    cur = conn.cursor()

    today = datetime.now().date()
    start_date = today - timedelta(days=days)
    end_date = today

    print(f"[refresh] 갱신 범위: {start_date} ~ {end_date}", flush=True)

    # 1. 기존 데이터 삭제 (texts·comments 양쪽 다 영향)
    print(f"[1/4] 기존 vocab_freq 삭제...", flush=True)
    t0 = time.time()
    cur.execute("""
        DELETE FROM vocab_freq
        WHERE freq_date >= %s AND freq_date < %s
    """, (start_date, end_date))
    deleted = cur.rowcount
    conn.commit()
    print(f"  → {deleted:,}행 삭제 ({time.time()-t0:.1f}초)", flush=True)

    # 2. text_meta 동기화 (texts 새 추가분만)
    print(f"[2/4] text_meta 동기화...", flush=True)
    t0 = time.time()
    cur.execute("""
        INSERT INTO text_meta (text_id, source_id, freq_date)
        SELECT t.text_id, t.source_id, t.published_at::date
        FROM texts t
        WHERE t.published_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM text_meta m WHERE m.text_id = t.text_id
          )
    """)
    new_meta = cur.rowcount
    conn.commit()
    print(f"  → {new_meta:,}행 추가 ({time.time()-t0:.1f}초)", flush=True)

    # 3. texts 빈도 집계 — morphemes (text_id) JOIN text_meta
    #    morphemes 한 텍스트 안 모든 occurrence 행 → GROUP BY COUNT(*) = TF
    print(f"[3/4] texts vocab_freq 재집계 (TF)...", flush=True)
    t0 = time.time()
    cur.execute("""
        INSERT INTO vocab_freq (lemma, pos, source_id, freq_date, count)
        SELECT m.lemma, m.pos, tm.source_id, tm.freq_date, COUNT(*)
        FROM morphemes m
        JOIN text_meta tm ON m.text_id = tm.text_id
        WHERE m.text_id IS NOT NULL
          AND tm.freq_date >= %s AND tm.freq_date < %s
        GROUP BY m.lemma, m.pos, tm.source_id, tm.freq_date
    """, (start_date, end_date))
    inserted = cur.rowcount
    conn.commit()
    print(f"  → {inserted:,}행 INSERT ({time.time()-t0:.1f}초)", flush=True)

    # 4. 댓글 빈도 집계 — morphemes (comment_id) JOIN comments
    #    source_id=7 (유튜브 댓글) 고정, comments.published_at을 freq_date로
    print(f"[4/4] 댓글 vocab_freq 집계 (TF, source_id=7)...", flush=True)
    t0 = time.time()
    cur.execute("""
        INSERT INTO vocab_freq (lemma, pos, source_id, freq_date, count)
        SELECT m.lemma, m.pos, 7, c.published_at::date, COUNT(*)
        FROM morphemes m
        JOIN comments c ON m.comment_id = c.comment_id
        WHERE m.comment_id IS NOT NULL
          AND c.published_at IS NOT NULL
          AND c.published_at::date >= %s
          AND c.published_at::date < %s
        GROUP BY m.lemma, m.pos, c.published_at::date
    """, (start_date, end_date))
    inserted_comments = cur.rowcount
    conn.commit()
    cur.close()
    print(f"  → {inserted_comments:,}행 INSERT ({time.time()-t0:.1f}초)", flush=True)


def refresh_lemma_summary(conn):
    """vocab_lemma_summary 테이블 통째로 재생성.

    vocab_freq 전체 GROUP BY로 단어별 누적 빈도 만듦.
    work_mem 2GB 임시 상향 (이 트랜잭션 한정).
    """
    cur = conn.cursor()

    print(f"[summary] vocab_lemma_summary 재생성...", flush=True)
    t0 = time.time()

    cur.execute("BEGIN")
    cur.execute("SET LOCAL work_mem = '2GB'")
    cur.execute("TRUNCATE vocab_lemma_summary")
    cur.execute("""
        INSERT INTO vocab_lemma_summary (lemma, pos, total_count)
        SELECT lemma, pos, SUM(count)::bigint
        FROM vocab_freq
        GROUP BY lemma, pos
    """)
    inserted = cur.rowcount
    cur.execute("COMMIT")
    cur.close()
    print(f"  → {inserted:,}행 ({time.time()-t0:.1f}초)", flush=True)


def refresh_neologism_candidates(conn):
    """미등재 신어 후보 재추출 (NNG/VV/VA).

    vocab_lemma_summary에서 우리말샘 미등재 단어 → neologism_candidates 적재.
    ON CONFLICT DO UPDATE로 score(빈도)만 갱신.
    """
    cur = conn.cursor()

    print(f"[neologism] NNG 추출...", flush=True)
    t0 = time.time()
    cur.execute("""
        INSERT INTO neologism_candidates (lemma, pos, detection_type, score, status)
        SELECT v.lemma, v.pos, 'unregistered', v.total_count, 'pending'
        FROM vocab_lemma_summary v
        WHERE v.pos = 'NNG'
          AND v.total_count >= 100
          AND char_length(v.lemma) >= 2
          AND v.lemma ~ '^[가-힣]+$'
          AND NOT EXISTS (
              SELECT 1 FROM urimalsaem_entries u
              WHERE u.headword_norm = v.lemma AND u.sense_type = '일반어'
          )
        ON CONFLICT (lemma, pos, detection_type)
        DO UPDATE SET score = EXCLUDED.score
    """)
    nng_count = cur.rowcount
    conn.commit()
    print(f"  → {nng_count:,}건 ({time.time()-t0:.1f}초)", flush=True)

    print(f"[neologism] VV/VA 추출...", flush=True)
    t0 = time.time()
    cur.execute("""
        INSERT INTO neologism_candidates (lemma, pos, detection_type, score, status)
        SELECT v.lemma, v.pos, 'unregistered', v.total_count, 'pending'
        FROM vocab_lemma_summary v
        WHERE v.pos IN ('VV', 'VA')
          AND v.total_count >= 100
          AND char_length(v.lemma) >= 3
          AND v.lemma ~ '^[가-힣]+다$'
          AND v.lemma !~ '(었다|았다|했다|왔다|였다|졌다|됐다|놨다|랐다|줬다|봤다|냈다)$'
          AND v.lemma !~ '(는다|인다|간다|온다|진다|된다|준다|낸다|본다|한다)$'
          AND v.lemma !~ '(볼다|줄다|져다|려다|질다|줘다|달다|갈다|봐다)$'
          AND NOT EXISTS (
              SELECT 1 FROM urimalsaem_entries u
              WHERE u.headword_norm = v.lemma AND u.sense_type = '일반어'
          )
        ON CONFLICT (lemma, pos, detection_type)
        DO UPDATE SET score = EXCLUDED.score
    """)
    vv_count = cur.rowcount
    conn.commit()
    print(f"  → {vv_count:,}건 ({time.time()-t0:.1f}초)", flush=True)

    cur.execute("""
        SELECT detection_type, pos, COUNT(*)
        FROM neologism_candidates
        WHERE detection_type = 'unregistered'
        GROUP BY detection_type, pos
        ORDER BY pos
    """)
    print("\n[현재 unregistered 후보 분포]")
    for row in cur.fetchall():
        print(f"  {row[1]:4s} {row[2]:>6,}건")
    cur.close()


def main():
    """일일 갱신 파이프라인:
    1. 최근 7일 vocab_freq 갱신 (texts·comments 양쪽)
    2. vocab_lemma_summary 재생성
    3. neologism_candidates 갱신
    """
    print(f"=== vocab/neologism 일일 갱신 시작: {datetime.now()} ===", flush=True)
    total_start = time.time()

    conn = get_conn()

    refresh_recent_days(conn, days=7)
    refresh_lemma_summary(conn)
    refresh_neologism_candidates(conn)

    conn.close()

    total = time.time() - total_start
    print(f"\n=== 완료. 총 {total:.0f}초 ({total/60:.1f}분) ===", flush=True)


if __name__ == '__main__':
    main()
