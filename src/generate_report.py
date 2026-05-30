"""주간 어휘 관측 보고서 생성."""
import os
import sys
import json
import math
from datetime import datetime, timedelta

# NER, Claude는 generate_report() 본체에서 lazy import (대시보드가 가져올 때 transformers 안 따라오게)

from anthropic import Anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from db import get_conn


REPORTS_DIR = "/home/ubuntu/lang-observatory/reports"


# 합성 동사 판정 — analyze_morphemes.py의 merge_tokens가 결합한 결과 사후 추정
# 패턴 ① NNG + XSV/XSA → ~받다, ~시키다 등
# 패턴 ② VV/VA + E + VX → ~주다, ~놓다, ~가다, ~지다 등
COMPOUND_VERB_SUFFIXES = (
    '주다', '받다', '시키다', '놓다', '가다', '오다',
    '내다', '버리다', '지다', '보다', '두다', '말다',
)


def is_compound_verb(lemma: str, pos: str) -> bool:
    """형태소 분석 시 보조용언/파생접사 결합으로 만들어진 lemma 판정."""
    if pos not in ('VV', 'VA'):
        return False
    if len(lemma) <= 2:
        return False
    return lemma.endswith(COMPOUND_VERB_SUFFIXES)


def get_claude_comment(report_md: str, model: str = "claude-sonnet-4-6") -> str:
    """보고서 마크다운 전체를 받아 한 단락 종합 코멘트를 생성한다.

    실패 시 빈 문자열 반환 (보고서 자체는 계속 생성되어야 함).
    """
    from anthropic import Anthropic

    prompt = f"""아래는 한국어 어휘 관측 시스템이 자동 생성한 주간 보고서야.
이 데이터를 종합해서 5~10줄 길이의 한 단락 코멘트를 한국어로 써줘.

코멘트에 포함되면 좋을 것:
- 이번 주의 가장 두드러진 사회·언어 흐름 (특정 사건, 키워드 묶음)
- 매체별 시기 차이 (네이버뉴스 vs 유튜브 댓글)
- 주목할 만한 신어 후보 1~2개와 그 의미적 신선도
- 데이터 한계나 노이즈 패턴이 보이면 짧게 짚기

형식:
- 마크다운 표 만들지 말고 자연스러운 한 단락 산문으로
- 5~10줄 정도 (한 줄 = 한 문장 기준)
- 결론적·평가적 표현 피하고 관측 보고에 맞게

보고서:
---
{report_md}
---

위 보고서의 종합 코멘트:"""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[!] Claude 코멘트 생성 실패: {e}")
        return ""


def get_freq_surge(cur, this_days=7, prev_days=28, top_n=10):
    """
    빈도 변화 Top.
    필터: NNG, length >= 2, 한글만, this 구간 빈도 >= min_cnt
    min_cnt는 this_days에 비례 (7일→50, 1일→약 7)

    반환:
      {
        "surge": [(lemma, this_cnt, prev_avg, ratio), ...],  # prev > 0, ratio 큰 순
        "new":   [(lemma, this_cnt), ...]                    # prev = 0, this_cnt 큰 순
      }
    """
    min_cnt = max(5, int(50 * this_days / 7))
    scale = prev_days / this_days

    cur.execute("""
        WITH this_period AS (
            SELECT lemma, pos, SUM(count) AS cnt
            FROM vocab_freq
            WHERE freq_date >= CURRENT_DATE - INTERVAL '%s days'
              AND pos = 'NNG'
              AND length(lemma) >= 2
              AND lemma ~ '^[가-힣]+$'
            GROUP BY lemma, pos
            HAVING SUM(count) >= %s
        ),
        prev_period AS (
            SELECT lemma, pos, SUM(count) / %s AS avg_cnt
            FROM vocab_freq
            WHERE freq_date >= CURRENT_DATE - INTERVAL '%s days'
              AND freq_date < CURRENT_DATE - INTERVAL '%s days'
              AND pos = 'NNG'
              AND length(lemma) >= 2
              AND lemma ~ '^[가-힣]+$'
            GROUP BY lemma, pos
        )
        SELECT
            t.lemma,
            t.cnt AS this_cnt,
            COALESCE(p.avg_cnt, 0) AS prev_avg
        FROM this_period t
        LEFT JOIN prev_period p ON t.lemma = p.lemma AND t.pos = p.pos
    """, (this_days, min_cnt, scale, this_days + prev_days, this_days))

    surge = []
    new = []
    for lemma, this_cnt, prev_avg in cur.fetchall():
        if prev_avg > 0:
            ratio = float(this_cnt) / float(prev_avg)
            surge.append((lemma, this_cnt, prev_avg, ratio))
        else:
            new.append((lemma, this_cnt))

    surge.sort(key=lambda x: x[3], reverse=True)
    new.sort(key=lambda x: x[1], reverse=True)

    return {
        "surge": surge[:top_n],
        "new": new[:top_n],
    }



def get_validations_this_week(cur, days=7):
    """이번 주에 들어간 sense_validation 결과들."""
    cur.execute("""
        SELECT headword, claude_result, judgment, n_clusters, created_at
        FROM sense_validation
        WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY created_at DESC
    """, (days,))
    return cur.fetchall()

def get_neologism_pool(cur, top_n=100):
    """누적 신어 후보 Top N. 3-1, 3-2 공용 풀."""
    cur.execute("""
        SELECT lemma, pos, detection_type, score, status
        FROM neologism_candidates
        WHERE detection_type = 'unregistered'
        ORDER BY score DESC
        LIMIT %s
    """, (top_n,))
    return cur.fetchall()


def get_emerging_pool(cur, days=7, top_n=100):
    """이번 주 떠오른 미등재어 Top N. LL 배수 계산용 데이터."""
    cur.execute("""
        WITH this_week AS (
            SELECT lemma, pos, SUM(count) AS cnt
            FROM vocab_freq
            WHERE freq_date >= CURRENT_DATE - INTERVAL '%s days'
              AND pos IN ('NNG', 'NNP', 'VV', 'VA')
              AND length(lemma) >= 2
              AND lemma ~ '^[가-힣]+$'
            GROUP BY lemma, pos
            HAVING SUM(count) >= 20
        ),
        prev_4w AS (
            SELECT lemma, pos, SUM(count) / 4.0 AS avg_cnt
            FROM vocab_freq
            WHERE freq_date >= CURRENT_DATE - INTERVAL '%s days'
              AND freq_date < CURRENT_DATE - INTERVAL '%s days'
              AND pos IN ('NNG', 'NNP', 'VV', 'VA')
              AND length(lemma) >= 2
              AND lemma ~ '^[가-힣]+$'
            GROUP BY lemma, pos
        ),
        unregistered AS (
            SELECT DISTINCT lemma, pos
            FROM neologism_candidates
            WHERE detection_type = 'unregistered'
        )
        SELECT
            t.lemma, t.pos, t.cnt AS this_cnt,
            COALESCE(p.avg_cnt, 0) AS prev_avg,
            CASE
                WHEN COALESCE(p.avg_cnt, 0) = 0 THEN 999.9
                ELSE t.cnt / p.avg_cnt
            END AS ratio
        FROM this_week t
        JOIN unregistered u ON t.lemma = u.lemma AND t.pos = u.pos
        LEFT JOIN prev_4w p ON t.lemma = p.lemma AND t.pos = p.pos
        ORDER BY ratio DESC
        LIMIT %s
    """, (days, days * 5, days, top_n))
    return cur.fetchall()


def get_emerging_neologisms(cur, this_days=7, prev_days=28, top_n=30):
    """
    떠오른 미등재어 Top.
    미등재어 중에서만 비교.
    min_cnt는 this_days에 비례 (7일→20, 1일→약 3)

    반환:
      {
        "surge": [(lemma, pos, this_cnt, prev_avg, ratio), ...],  # prev > 0, ratio 큰 순
        "new":   [(lemma, pos, this_cnt), ...]                    # prev = 0, this_cnt 큰 순
      }
    """
    min_cnt = max(3, int(20 * this_days / 7))
    scale = prev_days / this_days

    cur.execute("""
        WITH this_period AS (
            SELECT lemma, pos, SUM(count) AS cnt
            FROM vocab_freq
            WHERE freq_date >= CURRENT_DATE - INTERVAL '%s days'
              AND pos IN ('NNG', 'NNP', 'VV', 'VA')
              AND length(lemma) >= 2
              AND lemma ~ '^[가-힣]+$'
            GROUP BY lemma, pos
            HAVING SUM(count) >= %s
        ),
        prev_period AS (
            SELECT lemma, pos, SUM(count) / %s AS avg_cnt
            FROM vocab_freq
            WHERE freq_date >= CURRENT_DATE - INTERVAL '%s days'
              AND freq_date < CURRENT_DATE - INTERVAL '%s days'
              AND pos IN ('NNG', 'NNP', 'VV', 'VA')
              AND length(lemma) >= 2
              AND lemma ~ '^[가-힣]+$'
            GROUP BY lemma, pos
        ),
        unregistered AS (
            SELECT DISTINCT lemma, pos
            FROM neologism_candidates
            WHERE detection_type = 'unregistered'
        )
        SELECT
            t.lemma,
            t.pos,
            t.cnt AS this_cnt,
            COALESCE(p.avg_cnt, 0) AS prev_avg
        FROM this_period t
        JOIN unregistered u ON t.lemma = u.lemma AND t.pos = u.pos
        LEFT JOIN prev_period p ON t.lemma = p.lemma AND t.pos = p.pos
    """, (this_days, min_cnt, scale, this_days + prev_days, this_days))

    surge = []
    new = []
    for lemma, pos, this_cnt, prev_avg in cur.fetchall():
        if prev_avg > 0:
            ratio = float(this_cnt) / float(prev_avg)
            surge.append((lemma, pos, this_cnt, prev_avg, ratio))
        else:
            new.append((lemma, pos, this_cnt))

    surge.sort(key=lambda x: x[4], reverse=True)
    new.sort(key=lambda x: x[2], reverse=True)

    return {
        "surge": surge[:top_n],
        "new": new[:top_n],
    }


def get_top_by_source(cur, days=7, top_n=100):
    """매체별 이번 주 빈도 Top N. NNG/NNP/VV/VA 모두 포함.

    반환: {source_name: [(lemma, pos, cnt), ...]} — 매체별 빈도 내림차순.
    top_n을 넉넉히 뽑는 이유: 일반어/인물·단체 분리 + 합성 동사 제외 후에도
    각 표 30개씩 채우려면 풀이 커야 함.
    """
    cur.execute("""
        SELECT s.name, vf.lemma, vf.pos, SUM(vf.count) AS cnt
        FROM vocab_freq vf
        JOIN sources s ON vf.source_id = s.source_id
        WHERE vf.freq_date >= CURRENT_DATE - INTERVAL '%s days'
          AND vf.pos IN ('NNG', 'NNP', 'VV', 'VA')
          AND length(vf.lemma) >= 2
          AND vf.lemma ~ '^[가-힣]+$'
        GROUP BY s.name, vf.lemma, vf.pos
    """, (days,))

    rows = cur.fetchall()

    # 매체별로 모아서 정렬
    by_source = {}
    for source_name, lemma, pos, cnt in rows:
        by_source.setdefault(source_name, []).append((lemma, pos, cnt))

    # 각 매체 Top N (빈도 내림차순)
    result = {}
    for source_name, items in by_source.items():
        items.sort(key=lambda x: x[2], reverse=True)
        result[source_name] = items[:top_n]

    return result


def get_temporal_keyness_by_source(cur, this_days=7, prev_days=28, top_n=30):
    """
    매체별 시간 비교 키워드 분석.
    각 매체에서 이번 주(this_days) vs 지난 prev_days 키워드 비교 (Log-Likelihood).
    """
    # 매체별 이번 주 + 지난 기간 빈도 한 번에 가져오기
    cur.execute("""
        SELECT
            s.name,
            vf.lemma,
            SUM(CASE WHEN vf.freq_date >= CURRENT_DATE - INTERVAL '%s days' THEN vf.count ELSE 0 END) AS this_cnt,
            SUM(CASE WHEN vf.freq_date >= CURRENT_DATE - INTERVAL '%s days'
                      AND vf.freq_date < CURRENT_DATE - INTERVAL '%s days' THEN vf.count ELSE 0 END) AS prev_cnt
        FROM vocab_freq vf
        JOIN sources s ON vf.source_id = s.source_id
        WHERE vf.freq_date >= CURRENT_DATE - INTERVAL '%s days'
          AND vf.pos IN ('NNG', 'NNP')
          AND length(vf.lemma) >= 2
          AND vf.lemma ~ '^[가-힣]+$'
        GROUP BY s.name, vf.lemma
        HAVING SUM(CASE WHEN vf.freq_date >= CURRENT_DATE - INTERVAL '%s days' THEN vf.count ELSE 0 END) >= 5
    """, (this_days, this_days + prev_days, this_days, this_days + prev_days, this_days))

    rows = cur.fetchall()
    if not rows:
        return {}

    # 매체별 총합 계산
    by_source = {}
    for source_name, lemma, this_cnt, prev_cnt in rows:
        by_source.setdefault(source_name, []).append((lemma, this_cnt, prev_cnt))

    result = {}
    for source_name, items in by_source.items():
        # 이 매체의 총합
        this_total = float(sum(t for _, t, _ in items))
        prev_total = float(sum(p for _, _, p in items))
        grand_total = this_total + prev_total

        if this_total == 0 or prev_total == 0:
            continue

        scored = []
        for lemma, o1, o2 in items:
            o1, o2 = float(o1), float(o2)
            if o1 == 0:
                continue

            total_lemma = o1 + o2
            e1 = this_total * total_lemma / grand_total
            e2 = prev_total * total_lemma / grand_total

            ll = 0.0
            if o1 > 0 and e1 > 0:
                ll += o1 * math.log(o1 / e1)
            if o2 > 0 and e2 > 0:
                ll += o2 * math.log(o2 / e2)
            ll *= 2

            # 이번 주에 더 자주 나오는 단어만 (양의 키워드)
            this_ratio = o1 / this_total
            prev_ratio = o2 / prev_total if prev_total > 0 else 0
            if this_ratio > prev_ratio:
                scored.append((lemma, o1, o2, ll))

        scored.sort(key=lambda x: x[3], reverse=True)
        result[source_name] = scored[:top_n]

    return result

def get_registration_recommendations(cur, days=7):
    """이번 주 검증 결과 중 사전 등재 권고 후보."""
    cur.execute("""
        SELECT headword, claude_result, judgment
        FROM sense_validation
        WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
          AND judgment IN ('신어', '외래어합성', '의미분화')
        ORDER BY created_at DESC
    """, (days,))
    return cur.fetchall()


def generate_report():
    """주간 보고서 생성."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'analyzers'))
    from run_ner import classify_word_list

    conn = get_conn()
    cur = conn.cursor()

    today = datetime.now().date()
    week_start = today - timedelta(days=7)

    # 보고서 시작
    lines = []
    lines.append(f"# 한국어 어휘 관측 주간 보고서")
    lines.append("")
    lines.append(f"**기간**: {week_start} ~ {today}")
    lines.append(f"**생성일**: {today}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ---------- 풀 + NER 한 번에 (섹션 2 공용) ----------
    print("[보고서] 누적 풀 + 떠오른 풀 가져오기...")
    cumulative_pool = get_neologism_pool(cur, top_n=100)
    emerging_pool = get_emerging_pool(cur, top_n=100)

    # NER 적용 대상 = 두 풀의 (lemma, pos) 합집합
    all_words = set()
    for lemma, pos, _, _, _ in cumulative_pool:
        all_words.add((lemma, pos))
    for lemma, pos, _, _, _ in emerging_pool:
        all_words.add((lemma, pos))

    print(f"[보고서] NER 적용 대상: {len(all_words)}건")
    ner_results = classify_word_list(list(all_words), save=True, verbose=True)
    ner_map = {(r['lemma'], r['pos']): r['entity_type'] for r in ner_results}

    NAMED_ENTITY_TYPES = {'PS', 'OG', 'LC'}

    def is_general(lemma, pos):
        return ner_map.get((lemma, pos)) not in NAMED_ENTITY_TYPES

    def is_named(lemma, pos):
        return ner_map.get((lemma, pos)) in NAMED_ENTITY_TYPES

    entity_label = {'PS': '인물', 'OG': '단체·기관', 'LC': '장소'}

    # 섹션 2: 의미 검증 결과
    lines.append("## 1. 의미 검증 + 사전 등재 권고")
    lines.append("")
    lines.append("Claude가 클러스터·용례·사전 정보를 바탕으로 의미 분화를 판정한 결과와, 그중 등재 권고 대상으로 분류된 항목입니다.")
    lines.append("")

    # 1-A. 이번 주 검증된 단어 전체
    lines.append("### 1-A. 이번 주 의미 검증 결과")
    lines.append("")

    validations = get_validations_this_week(cur)

    if not validations:
        lines.append("*이번 주 검증 결과 없음.*")
    else:
        lines.append("| 단어 | 판정 | 의미 수 | 클러스터 수 | 정의문 (요약) |")
        lines.append("|---|---|---|---|---|")
        for headword, claude_result, judgment, n_clusters, _ in validations:
            # claude_result가 dict로 올지 str로 올지 모르니 둘 다 처리
            if isinstance(claude_result, str):
                claude_result = json.loads(claude_result)

            senses = claude_result.get("senses", [])
            n_senses = len(senses)

            # 첫 의미의 정의문 첫 80자
            if senses:
                definition = senses[0].get("definition", "")
                if len(definition) > 80:
                    definition = definition[:80] + "..."
            else:
                definition = ""

            # 표 안에서 | 글자가 들어가면 깨지니까 escape
            definition = definition.replace("|", "\\|")

            lines.append(f"| {headword} | {judgment} | {n_senses} | {n_clusters} | {definition} |")

    lines.append("")


    # 1-B. 등재 권고 (신어·외래어합성·의미분화로 판정된 것)
    lines.append("### 1-B. 사전 등재 권고 목록")
    lines.append("")
    lines.append("위 검증 결과 중 신어·외래어합성·의미분화로 판정된 항목입니다. 등재 결정 의사결정용.")
    lines.append("")

    recommendations = get_registration_recommendations(cur)

    if not recommendations:
        lines.append("*이번 주 등재 권고 항목 없음.*")
    else:
        lines.append("| 단어 | 판정 | 정의문 | 비고 |")
        lines.append("|---|---|---|---|")
        for headword, claude_result, judgment in recommendations:
            if isinstance(claude_result, str):
                claude_result = json.loads(claude_result)
            senses = claude_result.get("senses", [])
            if senses:
                definition = senses[0].get("definition", "")
            else:
                definition = ""
            notes = claude_result.get("notes", "")
            if len(notes) > 100:
                notes = notes[:100] + "..."
            definition = definition.replace("|", "\\|")
            notes = notes.replace("|", "\\|")
            lines.append(f"| {headword} | {judgment} | {definition} | {notes} |")

    lines.append("")

    # ---------- 섹션 2-1: 누적 미등재어 (일반어, 합성 동사 제외) ----------
    lines.append("## 2-1. 누적 미등재어 Top 30 (등재 권고 대상)")
    lines.append("")
    lines.append("누적 빈도가 높은 사전 미등재 일반어. 사전 등재 검토 대상.")
    lines.append("(NER로 인물·단체 제외 + 합성 동사 패턴 제외)")
    lines.append("")

    general_cumulative = [
        (lemma, pos, dtype, score, status)
        for lemma, pos, dtype, score, status in cumulative_pool
        if is_general(lemma, pos) and not is_compound_verb(lemma, pos)
    ][:30]

    if not general_cumulative:
        lines.append("*항목 없음.*")
    else:
        lines.append("| 순위 | 단어 | 품사 | 탐지 유형 | 누적 빈도 | 상태 |")
        lines.append("|---|---|---|---|---|---|")
        for i, (lemma, pos, dtype, score, status) in enumerate(general_cumulative, 1):
            score_str = f"{score:,.0f}" if score else "-"
            lines.append(f"| {i} | {lemma} | {pos} | {dtype} | {score_str} | {status} |")

    lines.append("")

    # ---------- 섹션 2-2: 떠오른 미등재어 (일반어, 합성 동사 제외) ----------
    lines.append("## 2-2. 이번 주 떠오른 미등재어 Top 30")
    lines.append("")
    lines.append("이번 주 빈도가 지난 4주 평균 대비 급증한 미등재 일반어. 새로운 사회적 현상의 신호.")
    lines.append("(NER로 인물·단체 제외 + 합성 동사 패턴 제외)")
    lines.append("")

    general_emerging = [
        (lemma, pos, this_cnt, prev_avg, ratio)
        for lemma, pos, this_cnt, prev_avg, ratio in emerging_pool
        if is_general(lemma, pos) and not is_compound_verb(lemma, pos)
    ][:30]

    if not general_emerging:
        lines.append("*항목 없음.*")
    else:
        lines.append("| 순위 | 단어 | 품사 | 이번 주 | 이전 4주 평균 | 배수 |")
        lines.append("|---|---|---|---|---|---|")
        for i, (lemma, pos, this_cnt, prev_avg, ratio) in enumerate(general_emerging, 1):
            ratio_str = f"{ratio:.1f}x" if ratio < 999 else "신규"
            lines.append(f"| {i} | {lemma} | {pos} | {this_cnt:,} | {prev_avg:.1f} | {ratio_str} |")

    lines.append("")

    # ---------- 섹션 2-3: 합성 동사 패턴 Top 30 (누적) ----------
    lines.append("## 2-3. 합성 동사 패턴 Top 30 (누적)")
    lines.append("")
    lines.append("형태소 분석에서 보조용언·파생접사 결합으로 만들어진 동사·형용사 lemma. ")
    lines.append("어휘 정착도 보기·분석 메타데이터로 활용.")
    lines.append(f"(매칭 어미: {', '.join('~'+s for s in COMPOUND_VERB_SUFFIXES)})")
    lines.append("")

    compound_cumulative = [
        (lemma, pos, dtype, score, status)
        for lemma, pos, dtype, score, status in cumulative_pool
        if is_compound_verb(lemma, pos)
    ][:30]

    if not compound_cumulative:
        lines.append("*항목 없음.*")
    else:
        lines.append("| 순위 | 단어 | 품사 | 탐지 유형 | 누적 빈도 | 상태 |")
        lines.append("|---|---|---|---|---|---|")
        for i, (lemma, pos, dtype, score, status) in enumerate(compound_cumulative, 1):
            score_str = f"{score:,.0f}" if score else "-"
            lines.append(f"| {i} | {lemma} | {pos} | {dtype} | {score_str} | {status} |")

    lines.append("")

    # 섹션 4: 매체별 키워드 분석 (Log-Likelihood)
    # 섹션 4: 매체별 시간 비교 키워드 분석
    # ---------- 섹션 2-4: NER 인물·단체 (떠오름 풀) ----------
    lines.append("## 2-4. 이번 주 떠오른 인물·단체 Top 30")
    lines.append("")
    lines.append("NER이 인물(PS)·단체·기관(OG)·장소(LC)로 분류한 단어 중 이번 주 떠오른 것.")
    lines.append("")

    named_emerging = [
        (lemma, pos, this_cnt, prev_avg, ratio)
        for lemma, pos, this_cnt, prev_avg, ratio in emerging_pool
        if is_named(lemma, pos)
    ][:30]

    if not named_emerging:
        lines.append("*항목 없음.*")
    else:
        lines.append("| 순위 | 단어 | 분류 | 이번 주 | 이전 4주 평균 | 배수 |")
        lines.append("|---|---|---|---|---|---|")
        for i, (lemma, pos, this_cnt, prev_avg, ratio) in enumerate(named_emerging, 1):
            ratio_str = f"{ratio:.1f}x" if ratio < 999 else "신규"
            et = ner_map.get((lemma, pos), '')
            label = entity_label.get(et, et)
            lines.append(f"| {i} | {lemma} | {label} | {this_cnt:,} | {prev_avg:.1f} | {ratio_str} |")

    lines.append("")

    lines.append("## 3. 매체별 시기 키워드 분석 (이번 주 vs 지난 4주)")
    lines.append("")
    lines.append("각 매체에서 지난 4주 대비 이번 주에 통계적으로 특이하게 자주 나온 단어입니다.")
    lines.append("LL이 클수록 시기 색깔이 뚜렷. (LL > 15.13 = 99.99% 신뢰수준)")
    lines.append("")

    by_source = get_temporal_keyness_by_source(cur)

    if not by_source:
        lines.append("*이번 주 데이터 없음.*")
    else:
        # 유튜브 영상은 description 길이 한계로 키워드가 빈약함 → 제외
        EXCLUDED_SOURCES = {"유튜브 영상"}
        source_names = sorted(s for s in by_source.keys() if s not in EXCLUDED_SOURCES)

        header = "| 순위 |" + "".join(f" {s} (단어 / 이번주 / 지난4주 / LL) |" for s in source_names)
        sep = "|---|" + "---|" * len(source_names)
        lines.append(header)
        lines.append(sep)

        for i in range(30):
            row = f"| {i+1} |"
            for s in source_names:
                items = by_source.get(s, [])
                if i < len(items):
                    lemma, this_cnt, prev_cnt, ll = items[i]
                    row += f" {lemma} / {this_cnt:,} / {prev_cnt:,} / {ll:.0f} |"
                else:
                    row += " - |"
            lines.append(row)

    lines.append("")

    # ---------- 섹션 4: Claude 코멘트 ----------
    # 위에서 만든 lines를 임시로 합쳐서 보고서 본문으로 전달
    report_so_far = "\n".join(lines)
    print("[보고서] Claude 코멘트 생성 중 (sonnet-4-6)...")
    comment = get_claude_comment(report_so_far)

    lines.append("## 4. Claude 종합 코멘트")
    lines.append("")
    if comment:
        lines.append(comment)
    else:
        lines.append("*코멘트 생성 실패.*")
    lines.append("")

    cur.close()

    # 파일 쓰기
    filename = f"weekly_report_{today.isoformat()}.md"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


if __name__ == "__main__":
    filepath = generate_report()
    print(f"보고서 생성: {filepath}")
