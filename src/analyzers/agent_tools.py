"""에이전트용 도구 함수.
각 함수는 DB 조회 결과를 dict로 반환. Claude가 받아서 자연어로 정리.
"""
import os
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_conn


def _expand_pos(pos):
    """'NNG·NNP' 같은 합쳐진 pos를 ANY() 매칭용 리스트로."""
    if pos is None:
        return None
    pos_list = pos.split("·") if "·" in pos else [pos]
    if "·" in pos:
        pos_list = pos_list + [pos]
    return pos_list


def lookup_word(lemma: str, pos: str = None) -> dict:
    """단어 한 개의 모든 정보를 모아서 반환.

    반환되는 dict:
      - lemma, pos
      - frequency: 총 빈도 + 등장 시기 범위
      - dict_entries: 세 사전의 등재 의미들
      - neologism_status: 신어 후보 등록 상태 (None이면 미등록)
      - validations: Claude로 검증한 결과 목록 (매체별, 시간순)
    """
    conn = get_conn()
    cur = conn.cursor()

    pos_list = _expand_pos(pos)

    # 1. 빈도
    if pos_list:
        cur.execute("""
            SELECT pos, SUM(count) AS total, MIN(freq_date), MAX(freq_date)
            FROM vocab_freq
            WHERE lemma = %s AND pos = ANY(%s)
            GROUP BY pos
        """, (lemma, pos_list))
    else:
        cur.execute("""
            SELECT pos, SUM(count) AS total, MIN(freq_date), MAX(freq_date)
            FROM vocab_freq
            WHERE lemma = %s
            GROUP BY pos
            ORDER BY total DESC
        """, (lemma,))
    freq_rows = cur.fetchall()

    if not freq_rows:
        cur.close()
        conn.close()
        return {"error": f"'{lemma}'에 대한 데이터가 없어요."}

    # pos 자동 추정: 인자로 안 주면 가장 흔한 pos
    if pos is None:
        pos = freq_rows[0][0]

    frequency = {
        "by_pos": [
            {
                "pos": p,
                "total_count": int(total),
                "first_seen": str(mn),
                "last_seen": str(mx),
            }
            for p, total, mn, mx in freq_rows
        ],
        "total_all_pos": sum(int(row[1]) for row in freq_rows),
    }

    # 2. 사전 등재 의미
    cur.execute("""
        SELECT dict_source, sense_number, pos, definition
        FROM urimalsaem_entries
        WHERE headword_norm = %s AND sense_type = '일반어'
        ORDER BY dict_source, sense_number
    """, (lemma,))
    dict_rows = cur.fetchall()

    dict_entries = {"urimalsaem": [], "stdict": [], "kbd": []}
    for src, sn, p, definition in dict_rows:
        dict_entries.setdefault(src, []).append({
            "sense_no": sn,
            "pos": p,
            "definition": definition,
        })

    # 3. 신어 후보 등록
    cur.execute("""
        SELECT status, detected_at FROM neologism_candidates
        WHERE lemma = %s
        ORDER BY detected_at DESC
        LIMIT 1
    """, (lemma,))
    neo_row = cur.fetchone()
    neologism_status = (
        {"status": neo_row[0], "detected_at": str(neo_row[1])} if neo_row else None
    )

    # 4. Claude 검증 결과 (있으면)
    cur.execute("""
        SELECT validation_id, pos, n_clusters, n_examples, judgment,
               claude_result, created_at
        FROM sense_validation
        WHERE headword = %s
        ORDER BY created_at DESC
    """, (lemma,))
    val_rows = cur.fetchall()

    validations = []
    for v_id, v_pos, n_cl, n_ex, judgment, claude_result, created_at in val_rows:
        if isinstance(claude_result, str):
            claude_result = json.loads(claude_result)

        senses_summary = []
        for s in claude_result.get("senses", []):
            senses_summary.append({
                "sense_no": s.get("sense_no"),
                "definition": s.get("definition"),
                "representative_example": s.get("representative_example", "")[:200],
                "dict_sense_matches": s.get("dict_sense_matches", {}),
            })

        # 매체 추정 — claude_result에 cluster_ids_merged 있으면 usage_clusters에서 source 조회
        all_cluster_ids = set()
        for s in claude_result.get("senses", []):
            all_cluster_ids.update(s.get("cluster_ids_merged", []))
        source_name = None
        if all_cluster_ids:
            cur.execute("""
                SELECT DISTINCT s.name FROM usage_clusters uc
                LEFT JOIN sources s ON s.source_id = uc.source_id
                WHERE uc.cluster_id = ANY(%s)
            """, (list(all_cluster_ids),))
            source_names = [r[0] for r in cur.fetchall() if r[0]]
            source_name = " · ".join(sorted(set(source_names))) if source_names else None

        validations.append({
            "validation_id": v_id,
            "pos": v_pos,
            "source_name": source_name,
            "n_clusters": n_cl,
            "n_examples": n_ex,
            "judgment": judgment,
            "created_at": str(created_at)[:10],
            "senses": senses_summary,
            "notes": claude_result.get("notes", ""),
            "system_diagnostics": claude_result.get("system_diagnostics", {}),
        })

    cur.close()
    conn.close()

    return {
        "lemma": lemma,
        "pos": pos,
        "frequency": frequency,
        "dict_entries": dict_entries,
        "neologism_status": neologism_status,
        "validations": validations,
    }

def freq_by_source(lemma: str, pos: str = None, days: int = 90) -> dict:
    """매체별 빈도 추이.

    반환되는 dict:
      - lemma, pos, days
      - by_source: 매체별 통계 (총 빈도, 첫·마지막 등장일, 최근 N일 평균)
      - peak_date: 단어 빈도가 가장 높았던 날짜 (어느 매체)
    """
    conn = get_conn()
    cur = conn.cursor()

    pos_list = _expand_pos(pos)
    cutoff_date = (datetime.now().date() - timedelta(days=days)).isoformat()

    if pos_list:
        cur.execute("""
            SELECT s.name, vf.freq_date, SUM(vf.count) AS cnt
            FROM vocab_freq vf
            LEFT JOIN sources s ON s.source_id = vf.source_id
            WHERE vf.lemma = %s AND vf.pos = ANY(%s)
              AND vf.freq_date >= %s
            GROUP BY s.name, vf.freq_date
            ORDER BY vf.freq_date
        """, (lemma, pos_list, cutoff_date))
    else:
        cur.execute("""
            SELECT s.name, vf.freq_date, SUM(vf.count) AS cnt
            FROM vocab_freq vf
            LEFT JOIN sources s ON s.source_id = vf.source_id
            WHERE vf.lemma = %s
              AND vf.freq_date >= %s
            GROUP BY s.name, vf.freq_date
            ORDER BY vf.freq_date
        """, (lemma, cutoff_date))
    rows = cur.fetchall()

    if not rows:
        cur.close()
        conn.close()
        return {"error": f"'{lemma}' 최근 {days}일 데이터 없음."}

    # 매체별 집계
    by_source = {}
    peak = {"count": 0, "date": None, "source": None}
    for source_name, freq_date, cnt in rows:
        sname = source_name or "(매체 미지정)"
        cnt = int(cnt)
        by_source.setdefault(sname, {
            "total": 0,
            "first_date": str(freq_date),
            "last_date": str(freq_date),
            "n_days_active": 0,
            "daily_counts": [],
        })
        bs = by_source[sname]
        bs["total"] += cnt
        bs["last_date"] = str(freq_date)
        bs["n_days_active"] += 1
        bs["daily_counts"].append((str(freq_date), cnt))

        if cnt > peak["count"]:
            peak = {"count": cnt, "date": str(freq_date), "source": sname}

    # daily_counts 너무 길면 잘라서 보내기 (각 매체별 상위 10일만)
    for sname, bs in by_source.items():
        bs["avg_daily"] = round(bs["total"] / bs["n_days_active"], 2)
        bs["top_days"] = sorted(bs["daily_counts"], key=lambda x: -x[1])[:10]
        del bs["daily_counts"]

    cur.close()
    conn.close()

    return {
        "lemma": lemma,
        "pos": pos,
        "days_window": days,
        "by_source": by_source,
        "peak": peak,
    }


def find_emerging_words(days: int = 7) -> dict:
    """최근 떠오른 단어 + 매체별 키워드.

    반환되는 dict:
      - surge: 평소보다 빈도 급증한 미등재어 (Top 15)
      - new: 이전 비교 구간에 없던 신규 등장 미등재어 (Top 15)
      - by_source: 매체별 LL 키워드 (각 매체 Top 10)
      - days_window
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from generate_report import (
        get_emerging_neologisms,
        get_temporal_keyness_by_source,
    )

    conn = get_conn()
    cur = conn.cursor()

    prev_days = days * 4 if days <= 7 else days * 2

    emerging = get_emerging_neologisms(cur, this_days=days, prev_days=prev_days, top_n=15)

    keyness = get_temporal_keyness_by_source(cur, this_days=days, prev_days=prev_days, top_n=10)

    # 유튜브 영상은 description 한계로 키워드 빈약 → 제외
    keyness = {k: v for k, v in keyness.items() if k != "유튜브 영상"}

    cur.close()
    conn.close()

    return {
        "days_window": days,
        "compare_with_prev_days": prev_days,
        "surge": [
            {"lemma": lemma, "pos": pos, "this_count": int(this_cnt),
             "prev_avg": round(float(prev_avg), 1), "ratio": round(float(ratio), 1)}
            for lemma, pos, this_cnt, prev_avg, ratio in emerging["surge"]
        ],
        "new": [
            {"lemma": lemma, "pos": pos, "this_count": int(this_cnt)}
            for lemma, pos, this_cnt in emerging["new"]
        ],
        "by_source": {
            source_name: [
                {"lemma": lemma, "this_count": int(t), "prev_count": int(p),
                 "log_likelihood": round(ll, 1)}
                for lemma, t, p, ll in items
            ]
            for source_name, items in keyness.items()
        },
    }


def validate_sense(lemma: str, pos: str, source_id: int) -> dict:
    """클러스터링 + Claude 검증을 한 번에 실행. 2~6분 걸림.

    반환되는 dict:
      - status: 'success' | 'failed' | 'no_clusters'
      - validation_id: 성공 시 sense_validation 테이블의 ID
      - n_clusters, n_examples
      - judgment: 신어 | 외래어합성 | 의미분화 | 변화없음
      - senses: [{sense_no, definition, representative_example, dict_sense_matches}, ...]
      - source_name
    """
    from analyzers.cluster_usage import run_cluster
    from analyzers.claude_analyzer import (
        fetch_word_data, build_prompt, call_claude, save_to_db,
    )

    conn = get_conn()
    cur = conn.cursor()

    # source_name 조회
    cur.execute("SELECT name FROM sources WHERE source_id = %s", (source_id,))
    row = cur.fetchone()
    source_name = row[0] if row else f"source_id={source_id}"

    # 기존 클러스터 있는지 확인
    cur.execute("""
        SELECT COUNT(*) FROM usage_clusters
        WHERE lemma = %s AND pos = %s AND source_id = %s
    """, (lemma, pos, source_id))
    has_clusters = cur.fetchone()[0] > 0
    cur.close()
    conn.close()

    # 1. 클러스터링 (없으면)
    if not has_clusters:
        print(f"[validate_sense] 클러스터링 시작: {lemma}/{pos} × {source_name}")
        cluster_result = run_cluster(lemma, pos, source_id)
        if cluster_result.get("status") != "success":
            return {
                "status": "failed",
                "stage": "clustering",
                "reason": cluster_result.get("status"),
                "details": cluster_result,
            }

    # 2. 검증 데이터 수집
    print(f"[validate_sense] 검증 데이터 모으는 중...")
    data = fetch_word_data(lemma, pos, source_id=source_id)
    if data is None:
        return {"status": "failed", "stage": "fetch_data"}

    # 3. Claude 호출
    print(f"[validate_sense] Claude 호출 중 (1~3분)...")
    prompt = build_prompt(data, source_name=source_name)
    result = call_claude(prompt)
    if result is None:
        return {"status": "failed", "stage": "claude_call"}

    # 4. DB 저장
    validation_id = save_to_db(lemma, data, result)

    # 5. 응답 정리
    senses_summary = []
    for s in result.get("senses", []):
        senses_summary.append({
            "sense_no": s.get("sense_no"),
            "definition": s.get("definition"),
            "representative_example": s.get("representative_example", "")[:200],
            "dict_sense_matches": s.get("dict_sense_matches", {}),
        })

    return {
        "status": "success",
        "validation_id": validation_id,
        "lemma": lemma,
        "pos": pos,
        "source_name": source_name,
        "n_clusters": len(data["clusters"]),
        "n_examples": sum(len(c["examples"]) for c in data["clusters"]),
        "judgment": result.get("judgment", ""),
        "senses": senses_summary,
        "notes": result.get("notes", ""),
        "system_diagnostics": result.get("system_diagnostics", {}),
    }

def system_overview() -> dict:
    """본 시스템이 지금까지 관측·발견한 결과 종합.

    반환되는 dict:
      - validations: 검증 누적 통계 + 단어별 요약
      - clustering: 클러스터링 진행 현황
      - neologisms: 신어 후보 등록 현황
      - corpus: 코퍼스 수집 현황 (매체별, 시기 범위)
      - self_diagnostics: 본 시스템이 자가 인식한 한계 모음
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. 검증 결과
    cur.execute("""
        SELECT validation_id, headword, pos, judgment, n_clusters, n_examples,
               claude_result, created_at
        FROM sense_validation
        ORDER BY created_at DESC
    """)
    val_rows = cur.fetchall()

    judgments = {}
    validated_words = []
    diagnostics_collected = []
    for v_id, hw, p, judgment, n_cl, n_ex, claude_result, created_at in val_rows:
        judgments[judgment] = judgments.get(judgment, 0) + 1

        if isinstance(claude_result, str):
            claude_result = json.loads(claude_result)

        # 첫 의미만 요약에 노출
        first_sense_def = ""
        senses = claude_result.get("senses", [])
        if senses:
            first_sense_def = senses[0].get("definition", "")[:80]

        validated_words.append({
            "validation_id": v_id,
            "lemma": hw,
            "pos": p,
            "judgment": judgment,
            "n_senses": len(senses),
            "first_sense": first_sense_def,
            "validated_on": str(created_at)[:10],
        })

        # 자가 진단 모음
        diag = claude_result.get("system_diagnostics", {})
        if diag and any(diag.values()):
            diagnostics_collected.append({
                "lemma": hw,
                "diagnostics": {k: v for k, v in diag.items() if v},
            })

    # 2. 클러스터링 현황
    cur.execute("""
        SELECT COUNT(DISTINCT (lemma, pos)) AS n_words,
               COUNT(DISTINCT (lemma, pos, source_id)) AS n_word_source_pairs,
               COUNT(*) AS n_clusters,
               SUM(member_count) AS n_total_members
        FROM usage_clusters
    """)
    n_words, n_pairs, n_clusters, n_members = cur.fetchone()

    # 매체별 클러스터링 단어 수
    cur.execute("""
        SELECT s.name, COUNT(DISTINCT uc.lemma) AS n_words
        FROM usage_clusters uc
        LEFT JOIN sources s ON s.source_id = uc.source_id
        GROUP BY s.name
        ORDER BY n_words DESC
    """)
    by_source_clustering = [
        {"source_name": name or "(매체 미지정)", "n_words": int(n)}
        for name, n in cur.fetchall()
    ]

    # 3. 신어 후보
    cur.execute("""
        SELECT status, COUNT(*) FROM neologism_candidates
        GROUP BY status
        ORDER BY COUNT(*) DESC
    """)
    neo_by_status = {status: int(cnt) for status, cnt in cur.fetchall()}

    # 4. 코퍼스 수집 현황
    cur.execute("""
        SELECT s.name,
               COUNT(t.text_id) AS n_texts,
               MIN(t.published_at)::date AS first_date,
               MAX(t.published_at)::date AS last_date
        FROM sources s
        LEFT JOIN texts t ON t.source_id = s.source_id
        GROUP BY s.name
        ORDER BY n_texts DESC
    """)
    corpus_texts = [
        {"source_name": name, "n_texts": int(n or 0),
         "first_date": str(fd) if fd else None,
         "last_date": str(ld) if ld else None}
        for name, n, fd, ld in cur.fetchall()
    ]

    cur.execute("""
        SELECT COUNT(*) AS n_comments,
               MIN(published_at)::date AS first_date,
               MAX(published_at)::date AS last_date
        FROM comments
    """)
    n_comments, c_first, c_last = cur.fetchone()
    corpus_comments = {
        "source_name": "유튜브 댓글",
        "n_comments": int(n_comments or 0),
        "first_date": str(c_first) if c_first else None,
        "last_date": str(c_last) if c_last else None,
    }

    cur.close()
    conn.close()

    return {
        "validations": {
            "total_validations": len(val_rows),
            "judgments": judgments,
            "validated_words": validated_words,
        },
        "clustering": {
            "n_unique_words": int(n_words or 0),
            "n_word_source_pairs": int(n_pairs or 0),
            "n_clusters_total": int(n_clusters or 0),
            "n_members_total": int(n_members or 0),
            "by_source": by_source_clustering,
        },
        "neologisms": {
            "by_status": neo_by_status,
        },
        "corpus": {
            "texts": corpus_texts,
            "comments": corpus_comments,
        },
        "self_diagnostics": diagnostics_collected,
    }


if __name__ == "__main__":
    # 테스트
    import pprint
    result = lookup_word("긁다", "VV")
    result = freq_by_source("긁다", "VV", days=365)
    result = find_emerging_words(days=7)
    result = system_overview()
    pprint.pprint(result, width=120)
