"""
이번 주 동향 페이지.
떠오른 미등재어 (분류별 분리 후 각자 Top N).
"""
import streamlit as st
import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/src")

from collections import Counter
from db import get_conn
import pandas as pd

st.set_page_config(page_title="어휘 사용 동향", layout="wide")

import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/dashboard")
from auth import check_password
from auth import AUTH_TOKEN
check_password()

st.title("어휘 사용 동향")

st.markdown("""
<style>
/* 1. 세련된 웹 폰트(Pretendard) 로드 및 앱 전체 적용 */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}

/* 타이틀 아이콘과 텍스트를 정렬하는 스타일 */

/* 아이콘 스타일 정의 (트렌드 차트 블루 톤) */

/* 타이틀 텍스트 스타일 정의 */

/* 2. 일반 마크다운 표를 프리미엄 데이터 테이블 UI로 전면 리모델링 */
table {
    width: 100% !important;
    max-width: 100% !important;
    border-collapse: collapse !important;
    margin: 0 !important;
}
th {
    background-color: #F8FAFC !important;
    color: #475569 !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    padding: 8px 12px !important;
    border-bottom: 2px solid #E2E8F0 !important;
    text-align: left !important;
}
td {
    padding: 8px 12px !important;
    font-size: 15px !important;
    color: #334155 !important;
    border-bottom: 1px solid #F1F5F9 !important;
}
tr:hover td {
    background-color: #F8FAFC !important;
}

/* 테이블 10개 수준 고정 스크롤 컨테이너 및 헤더 고정(Sticky) 정의 */
.scroll-container {
    max-height: 390px;
    overflow-y: auto;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin: 12px 0 24px 0;
}
.scroll-container th {
    position: sticky;
    top: 0;
    z-index: 10;
    box-shadow: 0 1px 0 #E2E8F0;
}

/* 품사/분류 알약 모양 배지 디자인 정의 */
code {
    background-color: #F1F5F9 !important;
    color: #475569 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    font-family: 'Pretendard', sans-serif !important;
}

/* 타이틀 가독성을 위한 헤더 마진 정돈 */
h2 {
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #1E293B !important;
    margin-top: 32px !important;
    margin-bottom: 16px !important;
}
h3 {
    font-size: 18px !important;
    font-weight: 600 !important;
    color: #334155 !important;
}

/* 테이블 링크 스타일 */
.scroll-container a {
    color: #2563EB !important;
    text-decoration: none !important;
}
.scroll-container a:hover {
    text-decoration: underline !important;
}
</style>
""", unsafe_allow_html=True)

# 타이틀 적용


@st.cache_data(ttl=3600, show_spinner="동향 데이터 가져오는 중...")
def load_emerging(this_days, prev_days, pool_size=500):
    from generate_report import get_emerging_neologisms
    conn = get_conn()
    cur = conn.cursor()
    result = get_emerging_neologisms(cur, this_days=this_days, prev_days=prev_days, top_n=pool_size)
    cur.close()
    conn.close()
    return result


@st.cache_data(ttl=3600)
def load_ner_map():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT lemma, pos, entity_type FROM ner_results")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {(lemma, pos): entity_type for lemma, pos, entity_type in rows}


COMPARISONS = {
    "오늘 vs 지난 28일": (1, 28),
    "이번 주 vs 지난 28일": (7, 28),
}

axis_label = st.radio("비교 축", list(COMPARISONS.keys()), horizontal=True, index=1)
this_days, prev_days = COMPARISONS[axis_label]
st.caption(f"최근 {this_days}일 vs 그 이전 {prev_days}일 평균 데이터 기준")
st.divider()


st.markdown("<h2>📈 사용 빈도 변화</h2>", unsafe_allow_html=True)

result = load_emerging(this_days, prev_days, pool_size=500)
ner_map = load_ner_map()

ENTITY_TAGS = {
    # KLUE-NER 태그 (옛 모델)
    "PS": "👤 인물",
    "OG": "🏢 단체",
    "LC": "📍 지명",
    "CV": "💼 직업",
    "AF": "🔧 사물",
    "EV": "📅 사건",
    "DT": "🗓 날짜",
    "TM": "⏰ 시간",
    "TI": "⏱ 기간",
    "QT": "🔢 수량",
    "AM": "🐾 동물",

    # Naver-NER 태그 (새 모델, 5/18~)
    "PER": "👤 인물",
    "ORG": "🏢 단체",
    "LOC": "📍 지명",
    "DAT": "🗓 날짜",
    "TIM": "⏰ 시간",
    "NUM": "🔢 수량",
    "AFW": "🔧 사물",
    "EVT": "📅 사건",
    "CVL": "🏛 문명",
    "TRM": "🔬 전문어",
    "MAT": "🪨 광물",
}

NAMED_ENTITIES = {
    # KLUE-NER
    "PS", "OG", "LC", "CV", "AF", "EV", "DT", "TM", "TI", "QT", "AM",
    # Naver-NER
    "PER", "ORG", "LOC", "DAT", "TIM", "NUM", "AFW", "EVT", "CVL", "TRM", "MAT",
}

# 💡 이렇게 수정 (덮어쓰기 하세요)
def get_entity(lemma, pos):
    # 1. 원래 들어온 품사(NNG 또는 NNP)로 DB 맵에서 먼저 찾습니다.
    res = ner_map.get((lemma, pos))
    if res:
        return res
    
    # 2. 만약 매칭에 실패했다면, NNG와 NNP를 서로 교차해서 한 번 더 찾아줍니다. (재처리 방지 패치)
    if pos == "NNG": return ner_map.get((lemma, "NNP"))
    if pos == "NNP": return ner_map.get((lemma, "NNG"))
    return None

def get_tag(lemma, pos):
    ent = get_entity(lemma, pos)
    if ent is None:
        return ""
    return ENTITY_TAGS.get(ent, f"❓ {ent}")


# 분류별 분리
def categorize(rows):
    general, named = [], []
    for row in rows:
        ent = get_entity(row[0], row[1])
        if ent in NAMED_ENTITIES:
            named.append(row)
        else:
            general.append(row)
    return general, named


surge_general, surge_named = categorize(result["surge"])
new_general,   new_named   = categorize(result["new"])

# 풀 분포 표시
all_pool = result["surge"] + result["new"]
dist = Counter()
for row in all_pool:
    ent = get_entity(row[0], row[1])
    dist[ent if ent else "일반어"] += 1

dist_parts = []
for ent, cnt in sorted(dist.items(), key=lambda x: -x[1]):
    if ent == "일반어":
        dist_parts.append(f"일반어 {cnt}")
    else:
        label = ENTITY_TAGS.get(ent, f"❓ {ent}")
        dist_parts.append(f"{label} {cnt}")
st.caption(f"이번 풀 분포 ({len(all_pool)}건): " + " · ".join(dist_parts))


# 분류 필터

filter_choice = st.radio(
    "분류 필터",
    ["일반어", "개체명"],
    horizontal=True,
)

if filter_choice == "일반어":
    surge_show = surge_general[:50]
    new_show   = new_general[:50]
else:
    surge_show = surge_named[:50]
    new_show   = new_named[:50]


SEARCH_PAGE = "/어휘_의미_탐색"

col_surge, col_new = st.columns(2)

with col_surge:
    st.markdown(f"### 📊 빈도 급등 ({len(surge_show)}건)")
    
    st.caption("이전에도 사용되던 단어 중 최근 사용량이 급격히 증가한 항목")

    if not surge_show:
        st.info("해당 분류에 단어가 없습니다.")
    else:
        # 공백 문자 버그 방지를 위해 한 줄 스타일로 결합
        html = "<div class='scroll-container'><table><thead><tr><th>단어</th><th>분류</th><th style='text-align: right;'>이번 빈도</th><th style='text-align: right;'>평소 빈도</th><th style='text-align: right;'>배수</th></tr></thead><tbody>"
        for lemma, pos, this_cnt, prev_avg, ratio in surge_show:
            tag = get_tag(lemma, pos)
            tag_str = f"<code>{tag}</code>" if tag else "-"
            html += f"<tr><td><a href='{SEARCH_PAGE}?word={lemma}&auth={AUTH_TOKEN}' target='_self'><strong>{lemma}</strong></a></td><td>{tag_str}</td><td style='text-align: right;'><strong>{this_cnt:,}</strong></td><td style='text-align: right;'>{float(prev_avg):.1f}</td><td style='text-align: right;'><code>{ratio:.1f}배</code></td></tr>"
        html += "</tbody></table></div>"
        st.markdown(html, unsafe_allow_html=True)

with col_new:
    st.markdown(f"### ✨ 신규 등장 ({len(new_show)}건)")
    st.caption("이전 비교 대상 구간에서는 발견되지 않았던 새로운 항목")

    if not new_show:
        st.info("해당 분류에 단어가 없습니다.")
    else:
        html = "<div class='scroll-container'><table><thead><tr><th>단어</th><th>분류</th><th style='text-align: right;'>이번 빈도</th></tr></thead><tbody>"
        for lemma, pos, this_cnt in new_show:
            tag = get_tag(lemma, pos)
            tag_str = f"<code>{tag}</code>" if tag else "-"
            html += f"<tr><td><a href='{SEARCH_PAGE}?word={lemma}&auth={AUTH_TOKEN}' target='_self'><strong>{lemma}</strong></a></td><td>{tag_str}</td><td style='text-align: right;'><strong>{this_cnt:,}</strong></td></tr>"
        html += "</tbody></table></div>"
        st.markdown(html, unsafe_allow_html=True)


# ---------- 매체별 시기 키워드 (Log-Likelihood) ----------
@st.cache_data(ttl=3600, show_spinner="매체별 키워드 계산 중...")
def load_keyness(this_days, prev_days, top_n=30):
    from generate_report import get_temporal_keyness_by_source
    conn = get_conn()
    cur = conn.cursor()
    result = get_temporal_keyness_by_source(cur, this_days=this_days, prev_days=prev_days, top_n=top_n)
    cur.close()
    conn.close()
    return result


st.markdown("<h2>🔍 매체별 키워드 (Log-Likelihood)</h2>", unsafe_allow_html=True)
st.caption(
   f"각 매체에서 최근 {this_days}일 구간 동안 통계적으로 특이한 출현 경향을 보인 명사(NNG·NNP) 목록입니다. "
    "상단 분류 필터 옵션이 동일하게 반영됩니다."
)

keyness = load_keyness(this_days, prev_days, top_n=50)
keyness = {k: v for k, v in keyness.items() if k != "유튜브 영상"}

if not keyness:
    st.info("이 비교 축에서는 조회된 매체별 키워드가 없습니다.")
else:
    source_columns = st.columns(len(keyness))
    for col, (source_name, items) in zip(source_columns, keyness.items()):
        with col:
            if filter_choice == "일반어":
                filtered = [r for r in items if get_entity(r[0], "NNG") not in NAMED_ENTITIES]
            else:
                filtered = [r for r in items if get_entity(r[0], "NNG") in NAMED_ENTITIES]
            shown = filtered[:50]

            st.markdown(f"### {source_name} ({len(shown)}건)")
            if not shown:
                st.info("조건에 맞는 단어가 없습니다.")
            else:
                html = "<div class='scroll-container'><table><thead><tr><th>단어</th><th>분류</th><th style='text-align: right;'>이번</th><th style='text-align: right;'>이전</th><th style='text-align: right;'>LL 지수</th></tr></thead><tbody>"
                for lemma, this_cnt, prev_cnt, ll in shown:
                    tag = get_tag(lemma, "NNG")
                    tag_str = f"<code>{tag}</code>" if tag else "-"
                    html += f"<tr><td><a href='{SEARCH_PAGE}?word={lemma}&auth={AUTH_TOKEN}' target='_self'><strong>{lemma}</strong></a></td><td>{tag_str}</td><td style='text-align: right;'>{this_cnt:,}</td><td style='text-align: right;'>{prev_cnt:,}</td><td style='text-align: right;'><code>LL {ll:.0f}</code></td></tr>"
                html += "</tbody></table></div>"
                st.markdown(html, unsafe_allow_html=True)


# ---------- 누적 미등재어 + 합성 동사 ----------
@st.cache_data(ttl=3600, show_spinner="누적 풀 가져오는 중...")
def load_cumulative_pool(top_n=300):
    from generate_report import get_neologism_pool
    conn = get_conn()
    cur = conn.cursor()
    result = get_neologism_pool(cur, top_n=top_n)
    cur.close()
    conn.close()
    return result


st.divider()
st.markdown("<h2>📚 누적 미등재어 분석 (전체 기간 기준)</h2>", unsafe_allow_html=True)
st.caption("비교 축 설정과 무관하게 시스템 전체에 누적된 빈도를 기준으로 정렬한 사전 등재 검토 대상 가용 풀입니다.")

cumulative_pool = load_cumulative_pool(top_n=300)

from generate_report import is_compound_verb

general_cumulative = []
compound_cumulative = []
for lemma, pos, dtype, score, status in cumulative_pool:
    if is_compound_verb(lemma, pos):
        compound_cumulative.append((lemma, pos, dtype, score, status))
    else:
        ent = get_entity(lemma, pos)
        if ent in NAMED_ENTITIES:
            continue
        general_cumulative.append((lemma, pos, dtype, score, status))

col_general, col_compound = st.columns(2)

with col_general:
    # 요청하신 대로 100개 노출로 확장 및 HTML 인덴트 버그 수정
    shown = general_cumulative[:100]
    st.markdown(f"### 📂 일반 어휘 계열 ({len(shown)}건)")
    st.caption("고유명사(NER) 및 파생/합성 동사 패턴을 제외한 일반 어휘 단위 (최대 100개 스크롤 가능)")
    
    html = "<div class='scroll-container'><table><thead><tr><th>단어</th><th style='text-align: center;'>품사</th><th>분류</th><th style='text-align: right;'>누적 빈도</th></tr></thead><tbody>"
    for lemma, pos, dtype, score, status in shown:
        tag = get_tag(lemma, pos)
        tag_str = f"<code>{tag}</code>" if tag else "-"
        score_str = f"<strong>{score:,.0f}</strong>" if score else "-"
        html += f"<tr><td><a href='{SEARCH_PAGE}?word={lemma}&auth={AUTH_TOKEN}' target='_self'><strong>{lemma}</strong></a></td><td style='text-align: center;'><code>{pos}</code></td><td>{tag_str}</td><td style='text-align: right;'>{score_str}</td></tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)

with col_compound:
    # 요청하신 대로 100개 노출로 확장 및 HTML 인덴트 버그 수정
    shown = compound_cumulative[:100]
    st.markdown(f"### 🔗 결합 동사 패턴 ({len(shown)}건)")
    st.caption("~주다, ~받다, ~시키다 등 보조용언 및 파생접사가 결합된 문형 단위 (최대 100개 스크롤 가능)")
    
    html = "<div class='scroll-container'><table><thead><tr><th>단어</th><th style='text-align: center;'>품사</th><th style='text-align: right;'>누적 빈도</th></tr></thead><tbody>"
    for lemma, pos, dtype, score, status in shown:
        score_str = f"<strong>{score:,.0f}</strong>" if score else "-"
        html += f"<tr><td><a href='{SEARCH_PAGE}?word={lemma}&auth={AUTH_TOKEN}' target='_self'><strong>{lemma}</strong></a></td><td style='text-align: center;'><code>{pos}</code></td><td style='text-align: right;'>{score_str}</td></tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)

st.divider()
