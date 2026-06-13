import streamlit as st
import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/src")
from db import get_conn
from kwic import make_kwic
import json
import pandas as pd
import re
import plotly.express as px
from collections import defaultdict
import html


def expand_pos(pos: str) -> list[str]:
    """'NNG·NNP' 같은 합쳐진 pos를 리스트로 펼침."""
    return pos.split("·") if "·" in pos else [pos]

st.set_page_config(page_title="어휘 의미 탐색", layout="wide")

st.markdown("""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 16px; color: white; margin-bottom: 24px;'>
<div style='font-size: 28px; font-weight: 700; margin-bottom: 8px;'>🔍 어휘 의미 탐색</div>
<div style='font-size: 16px; opacity: 0.95;'>단어별 사용 빈도, 사전 정보, 실제 용례를 상세하게 확인</div>
</div>""", unsafe_allow_html=True)

st.markdown("""
<style>
/* 1. 세련된 웹 폰트(Pretendard) 로드 및 앱 전체 적용 */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}

/* 타이틀 아이콘과 텍스트를 정렬하는 스타일 */

/* 아이콘 스타일 정의 (고급스러운 블루 톤) */

/* 타이틀 텍스트 스타일 정의 */

/* 2. 마크다운 표 스타일 정돈 */
table {
    width: auto !important;
    min-width: 60%;
    max-width: 800px;
    border-collapse: collapse;
}
table td, table th {
    padding: 6px 14px !important;
    border-bottom: 1px solid #F1F5F9 !important;
}

/* 3. 투박한 Expander를 세련된 '카드' 디자인으로 변경 */
[data-testid="stExpander"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03) !important;
    margin-top: 6px !important;
    margin-bottom: 6px !important;
    transition: all 0.2s ease-in-out !important;
}

/* 카드 내부 여백 미세 조절 */
[data-testid="stExpanderDetails"] {
    padding-top: 12px !important;
    padding-bottom: 12px !important;
}

/* 카드에 마우스 올렸을 때 강조 효과 */
[data-testid="stExpander"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.08) !important;
    transform: translateY(-1px);
}

/* 카드 내부 타이틀 텍스트 색상 정돈 */
[data-testid="stExpander"] summary p {
    font-size: 15px !important;
    color: #1E293B !important;
}

/* 팝오버 및 일반 실행 버튼 일괄 모던화 및 크기 정돈 */
div[data-testid="stPopover"] > button, div[data-testid="stButton"] > button {
    width: 100% !important;
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    color: #475569 !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 8px 14px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    transition: all 0.2s ease !important;
}

div[data-testid="stPopover"] > button:hover, div[data-testid="stButton"] > button:hover {
    background-color: #F1F5F9 !important;
    border-color: #CBD5E1 !important;
    color: #0F172A !important;
}

/* 검색창 디자인 */
input[type="text"] {
    border: 2px solid #E2E8F0 !important;
    border-radius: 10px !important;
    padding: 12px 16px !important;
    font-size: 15px !important;
    transition: all 0.2s ease !important;
}
input[type="text"]:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
}

/* Dataframe 테이블 디자인 */
[data-testid="stDataFrame"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
[data-testid="stDataFrame"] thead {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
}
[data-testid="stDataFrame"] thead th {
    color: white !important;
    font-weight: 600 !important;
    padding: 12px !important;
}
[data-testid="stDataFrame"] tbody tr:hover {
    background-color: #F8FAFC !important;
}

/* Metric 카드 디자인 */
[data-testid="stMetric"] {
    background-color: #F8FAFC !important;
    padding: 16px !important;
    border-radius: 10px !important;
    border: 1px solid #E2E8F0 !important;
}

/* 사이드바 디자인 */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #667eea 0%, #764ba2 100%) !important;
}
section[data-testid="stSidebar"] > div {
    background: transparent !important;
}
section[data-testid="stSidebar"] * {
    color: white !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {
    color: white !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div {
    color: rgba(255, 255, 255, 0.95) !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.3) !important;
    margin: 20px 0 !important;
}
section[data-testid="stSidebar"] button {
    background-color: rgba(255, 255, 255, 0.2) !important;
    color: white !important;
    border: 1px solid rgba(255, 255, 255, 0.4) !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
    padding: 10px 16px !important;
}
section[data-testid="stSidebar"] button:hover {
    background-color: rgba(255, 255, 255, 0.3) !important;
    border-color: rgba(255, 255, 255, 0.6) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
}
section[data-testid="stSidebar"] button p {
    color: white !important;
    font-weight: 500 !important;
}
</style>
""", unsafe_allow_html=True)

# 고급스러운 돋보기 SVG 타이틀 레이아웃 생성


# ---------- 검색창 ----------
default_query = st.query_params.get("word", "")

query = st.text_input(
    "검색어",
    value=default_query,
    placeholder="단어를 입력하세요",
    help="2글자 이상 입력하면 전방 일치로 후보를 보여줍니다.",
)


# ---------- 부분 일치 후보 조회 ----------
@st.cache_data(ttl=60)

@st.cache_data(ttl=60)
def fetch_candidates(query: str, limit: int = 50):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH dict_summary AS (
            SELECT
                headword_norm,
                SUM(CASE WHEN dict_source = 'urimalsaem' THEN 1 ELSE 0 END) AS uri,
                SUM(CASE WHEN dict_source = 'stdict' THEN 1 ELSE 0 END) AS std,
                SUM(CASE WHEN dict_source = 'kbd' THEN 1 ELSE 0 END) AS kbd
            FROM urimalsaem_entries
            WHERE headword_norm LIKE %s
            GROUP BY headword_norm
        ),
        neo_summary AS (
            SELECT lemma, pos, MAX(status) AS status
            FROM neologism_candidates
            WHERE lemma LIKE %s
            GROUP BY lemma, pos
        ),
        vocab_grouped AS (
            SELECT
                lemma,
                CASE
                    WHEN pos IN ('NNG', 'NNP') THEN 'NNG·NNP'
                    ELSE pos
                END AS pos_group,
                STRING_AGG(DISTINCT pos, '·' ORDER BY pos) AS pos_display,
                SUM(total_count) AS total_count
            FROM vocab_lemma_summary
            WHERE lemma LIKE %s
            GROUP BY lemma, pos_group
        )
        SELECT
            vg.lemma,
            vg.pos_display AS pos,
            vg.total_count,
            COALESCE(d.uri, 0) AS uri,
            COALESCE(d.std, 0) AS std,
            COALESCE(d.kbd, 0) AS kbd,
            ns.status AS neo_status
        FROM vocab_grouped vg
        LEFT JOIN dict_summary d ON d.headword_norm = vg.lemma
        LEFT JOIN neo_summary ns
            ON ns.lemma = vg.lemma
           AND (
                ns.pos = vg.pos_display
                OR (vg.pos_display = 'NNG·NNP' AND ns.pos IN ('NNG', 'NNP'))
           )
        ORDER BY vg.total_count DESC
        LIMIT %s
    """, (query + "%", query + "%", query + "%", limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(
        rows,
        columns=["lemma", "pos", "total_count", "uri", "std", "kbd", "neo_status"],
    )


# ---------- 선택 처리 ----------
selected_lemma = None
selected_pos = None

if not query:
    # 초기 화면 - 기능 안내
    st.markdown("### 🔍 어휘 의미 탐색")

    st.markdown("""
    단어를 검색하면 다음 정보를 확인할 수 있습니다:

    - 📊 **사용 빈도**: 코퍼스 내 출현 빈도와 기간
    - 📖 **사전 정보**: 우리말샘, 표준국어대사전, 기초사전 비교
    - 📈 **시계열 분석**: 매체별 사용 추이 그래프
    - 💬 **실제 용례**: 시점별 사용 예시
    - 🆕 **신어 정보**: 신어 후보 등록 여부
    """)

    st.info("👆 위 검색창에 단어를 입력하세요")
    st.stop()
else:
    df_cand = fetch_candidates(query)
    if df_cand.empty:
        st.warning(f"'{query}'(으)로 시작하는 단어가 없어요.")
        st.stop()

    st.markdown(f"### 탐색할 단어 선택 (후보 {len(df_cand)}건)")
    st.caption("단어를 선택하면 상세 정보를 확인할 수 있습니다.")

    df_display = df_cand.copy()
    for col in ["uri", "std", "kbd"]:
        df_display[col] = df_display[col].apply(lambda x: x if x > 0 else None)
    df_display["neo_status"] = df_display["neo_status"].fillna("")

    event = st.dataframe(
        df_display,
        column_config={
            "lemma": st.column_config.TextColumn("단어", width="medium"),
            "pos": st.column_config.TextColumn("품사", width="small"),
            "total_count": st.column_config.NumberColumn("빈도", format="%d"),
            "uri": st.column_config.NumberColumn("우리말샘", format="%d", help="우리말샘에 등재된 sense 수"),
            "std": st.column_config.NumberColumn("표준국어대", format="%d", help="표준국어대사전에 등재된 sense 수"),
            "kbd": st.column_config.NumberColumn("기초사전", format="%d", help="한국어기초사전에 등재된 sense 수"),
            "neo_status": st.column_config.TextColumn("신어 후보", help="neologism_candidates 상태"),
        },
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="cand_table",
    )
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_lemma = df_cand.iloc[idx]["lemma"]
        selected_pos = df_cand.iloc[idx]["pos"]

if not selected_lemma:
    st.info("표에서 단어를 선택하면 아래에 상세 정보가 떠요.")
    st.stop()

st.divider()
# 배지 스타일 적용된 단어 헤더
st.markdown(f"## 📌 **{selected_lemma}** &nbsp;`{selected_pos}`")

lemma = selected_lemma
pos = selected_pos


# ---------- 기본 정보 조회 ----------
@st.cache_data(ttl=60)
def fetch_basic_info(lemma: str, pos: str | None):
    conn = get_conn()
    cur = conn.cursor()

    if pos:
        cur.execute("""
            SELECT pos, SUM(count) AS total, MIN(freq_date), MAX(freq_date)
            FROM vocab_freq
            WHERE lemma = %s AND pos = ANY(%s)
            GROUP BY pos
        """, (lemma, expand_pos(pos)))
    else:
        cur.execute("""
            SELECT pos, SUM(count) AS total, MIN(freq_date), MAX(freq_date)
            FROM vocab_freq
            WHERE lemma = %s
            GROUP BY pos
            ORDER BY total DESC
        """, (lemma,))
    freq_rows = cur.fetchall()

    cur.execute("""
        SELECT dict_source, COUNT(*) AS sense_count
        FROM urimalsaem_entries
        WHERE headword_norm = %s
        GROUP BY dict_source
        ORDER BY dict_source
    """, (lemma,))
    dict_rows = cur.fetchall()

    cur.execute("""
        SELECT candidate_id, pos, status, detected_at
        FROM neologism_candidates
        WHERE lemma = %s
    """, (lemma,))
    cand_rows = cur.fetchall()

    # 임베딩 건수 조회 (segment_lemma_map 기준)
    if pos:
        cur.execute("""
            SELECT COUNT(DISTINCT m.embedding_id)
            FROM segment_lemma_map m
            WHERE m.lemma = %s AND m.pos = ANY(%s)
        """, (lemma, expand_pos(pos)))
    else:
        cur.execute("""
            SELECT COUNT(DISTINCT m.embedding_id)
            FROM segment_lemma_map m
            WHERE m.lemma = %s
        """, (lemma,))
    embedding_count = cur.fetchone()[0] if cur.rowcount > 0 else 0

    cur.close()
    conn.close()
    return freq_rows, dict_rows, cand_rows, embedding_count


freq_rows, dict_rows, cand_rows, embedding_count = fetch_basic_info(lemma, pos)

if not freq_rows:
    st.warning(f"'{lemma}' (품사={pos}) — `vocab_freq`에 데이터 없음")
    st.stop()

st.divider()

# 빈도

# 빈도
st.markdown("#### 📊 빈도 (vocab_freq)")

# NNG·NNP는 한 카드로 합쳐서 표시
if "·" in pos:
    total_sum = sum(row[1] for row in freq_rows)
    min_dates = [row[2] for row in freq_rows if row[2]]
    max_dates = [row[3] for row in freq_rows if row[3]]
    mn = min(min_dates) if min_dates else None
    mx = max(max_dates) if max_dates else None
    pos_labels = "·".join(row[0] for row in freq_rows)
    st.metric(
        label=f"품사 {pos_labels}",
        value=f"{total_sum:,}회",
        help=f"{mn} ~ {mx}"
    )
else:
    freq_cols = st.columns(len(freq_rows))
    for i, (p, total, mn, mx) in enumerate(freq_rows):
        with freq_cols[i]:
            st.metric(
                label=f"품사 {p}",
                value=f"{total:,}회",
                help=f"{mn} ~ {mx}"
            )

# 임베딩 건수 표시
st.caption(f"💡 **임베딩 대상 세그먼트**: {embedding_count:,}건 (실제 빈도와 다를 수 있음. 300자 세그먼트 단위로 집계)")

st.divider()

# ---------- 사전 sense 상세 함수 ----------
@st.cache_data(ttl=300)
def fetch_dict_senses(lemma: str, dict_source: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT sense_number, pos, definition, examples, sense_category, link
        FROM urimalsaem_entries
        WHERE headword_norm = %s AND dict_source = %s
        ORDER BY sense_number ASC
    """, (lemma, dict_source))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def render_example(ex: dict) -> str:
    text = ex.get("example", "")
    text = re.sub(r"\{([^}]+)\}", r"**\1**", text)
    src = ex.get("source")
    if src:
        return f"- {text} *≪{src}≫*"
    return f"- {text}"


def render_dict_senses(lemma: str, dict_source: str):
    senses = fetch_dict_senses(lemma, dict_source)
    if not senses:
        st.info("이 사전에는 등재되지 않음")
        return

    if dict_source == "stdict":
        st.caption("※ 번호는 sense_code 오름차순. 표준국어대 웹사전 화면 번호와 거의 일치합니다.")

    dict_colors = {
        "urimalsaem": "#10b981",
        "stdict": "#3b82f6",
        "kbd": "#8b5cf6"
    }
    dict_names = {
        "urimalsaem": "우리말샘",
        "stdict": "표준국어대사전",
        "kbd": "한국어기초사전"
    }

    color = dict_colors.get(dict_source, "#64748b")
    dict_name = dict_names.get(dict_source, dict_source)

    for idx, (sn, p, definition, examples, sense_cat, link) in enumerate(senses, 1):
        label_num = idx if dict_source == "stdict" else sn

        # 카드 스타일 렌더링
        safe_definition = html.escape(definition) if definition else ""

        meta_badges = []
        if p:
            meta_badges.append(f"<span style='background: #f1f5f9; color: #475569; padding: 2px 8px; border-radius: 4px; font-size: 12px;'>품사 {html.escape(p)}</span>")
        if sense_cat:
            meta_badges.append(f"<span style='background: #f1f5f9; color: #475569; padding: 2px 8px; border-radius: 4px; font-size: 12px;'>범주 {html.escape(sense_cat)}</span>")

        card_html = f"""<div style='background: #f8fafc; border-left: 4px solid {color}; padding: 16px; border-radius: 8px; margin: 12px 0;'>
<div style='margin-bottom: 8px;'>
<span style='font-size: 16px; font-weight: 700; color: #1e293b;'>의미 {label_num}</span>
{f"<span style='background: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px;'>{dict_name}</span>" if dict_source == "stdict" else ""}
{f"<span style='color: #64748b; font-size: 12px; margin-left: 8px;'>sense_code {sn}</span>" if dict_source == "stdict" else ""}
</div>
<div style='font-size: 16px; font-weight: 500; color: #334155; margin: 12px 0; line-height: 1.6;'>
{safe_definition}
</div>
{f"<div style='margin-top: 10px;'>{' '.join(meta_badges)}</div>" if meta_badges else ""}
</div>"""

        st.markdown(card_html, unsafe_allow_html=True)

        # 예문은 expander로
        if examples:
            with st.expander(f"📝 예문 {len(examples)}개 보기", expanded=False):
                for ex in examples:
                    st.markdown(render_example(ex))

        if link:
            st.caption(f"🔗 [원문 링크]({link})")


st.divider()

# ---------- 사전 등재 ----------
st.markdown("#### 📖 사전 정보")
if not dict_rows:
    st.markdown("""<div style='background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 6px; margin: 12px 0;'>
<span style='color: #991b1b; font-weight: 600;'>🚫 미등재</span>
<span style='color: #7f1d1d; margin-left: 8px;'>세 사전 어디에도 등재되지 않았습니다</span>
</div>""", unsafe_allow_html=True)
else:
    dict_label = {
        "urimalsaem": "우리말샘",
        "stdict": "표준국어대사전",
        "kbd": "한국어기초사전",
    }
    by_source = {ds: cnt for ds, cnt in dict_rows}
    available_dicts = [s for s in ["urimalsaem", "stdict", "kbd"] if s in by_source]
    missing_dicts = [s for s in ["urimalsaem", "stdict", "kbd"] if s not in by_source]

    # 등재 현황 배지
    status_badges = []
    for s in ["urimalsaem", "stdict", "kbd"]:
        if s in by_source:
            status_badges.append(f"<span style='background: #10b981; color: white; padding: 4px 10px; border-radius: 6px; font-size: 13px; margin-right: 6px;'>✓ {dict_label[s]} ({by_source[s]})</span>")
        else:
            status_badges.append(f"<span style='background: #f59e0b; color: white; padding: 4px 10px; border-radius: 6px; font-size: 13px; margin-right: 6px;'>✗ {dict_label[s]}</span>")

    st.markdown(f"<div style='margin: 12px 0;'>{''.join(status_badges)}</div>", unsafe_allow_html=True)

    tab_labels = [f"{dict_label[s]} ({by_source[s]}개 sense)" for s in available_dicts]
    tabs = st.tabs(tab_labels)
    for tab, src in zip(tabs, available_dicts):
        with tab:
            render_dict_senses(lemma, src)

st.divider()

# 신어 후보
st.markdown("#### 🆕 신어 후보 등록 여부")
if not cand_rows:
    st.markdown("""<div style='background: #f8fafc; border-left: 4px solid #94a3b8; padding: 12px 16px; border-radius: 6px; margin: 12px 0;'>
<span style='color: #64748b;'>등록되지 않음</span>
</div>""", unsafe_allow_html=True)
else:
    for cid, p, status, detected_at in cand_rows:
        status_color = "#10b981" if status == "confirmed" else "#f59e0b"
        card_html = f"""<div style='background: #f8fafc; border-left: 4px solid {status_color}; padding: 14px 18px; border-radius: 8px; margin: 12px 0;'>
<div style='margin-bottom: 6px;'>
<span style='background: {status_color}; color: white; padding: 3px 10px; border-radius: 6px; font-size: 13px; font-weight: 600;'>🆕 신어 후보</span>
<span style='color: #64748b; font-size: 13px; margin-left: 10px;'>ID: {cid}</span>
</div>
<div style='margin-top: 8px; color: #334155; font-size: 14px;'>
<span style='background: #f1f5f9; color: #475569; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin-right: 8px;'>품사 {html.escape(p)}</span>
<span style='background: {status_color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin-right: 8px;'>{html.escape(status)}</span>
<span style='color: #64748b; font-size: 13px;'>📅 첫 발견: {detected_at}</span>
</div>
</div>"""
        st.markdown(card_html, unsafe_allow_html=True)

st.divider()

# ---------- 시계열 그래프 ----------
st.markdown("### 📈 매체별 추세 그래프")

ctrl1, ctrl2 = st.columns(2)
with ctrl1:
    period = st.radio(
        "기간",
        ["최근 90일", "최근 1년", "최근 5년", "전체"],
        horizontal=True,
        index=3,
    )
with ctrl2:
    agg = st.radio(
        "집계 단위",
        ["일별", "주별", "월별"],
        horizontal=True,
        index=2,
    )


@st.cache_data(ttl=60)
def fetch_freq_trend(lemma: str, pos: str | None):
    conn = get_conn()
    cur = conn.cursor()
    if pos:
        cur.execute("""
            SELECT vf.freq_date, s.name AS source_name, SUM(vf.count) AS cnt
            FROM vocab_freq vf
            LEFT JOIN sources s ON s.source_id = vf.source_id
            WHERE vf.lemma = %s AND vf.pos = ANY(%s)
            GROUP BY vf.freq_date, s.name
            ORDER BY vf.freq_date
        """, (lemma, expand_pos(pos)))

    else:
        cur.execute("""
            SELECT vf.freq_date, s.name AS source_name, SUM(vf.count) AS cnt
            FROM vocab_freq vf
            LEFT JOIN sources s ON s.source_id = vf.source_id
            WHERE vf.lemma = %s
            GROUP BY vf.freq_date, s.name
            ORDER BY vf.freq_date
        """, (lemma,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(rows, columns=["freq_date", "source_name", "count"])

df = fetch_freq_trend(lemma, pos)

if df.empty:
    st.info("시계열 데이터 없음")
else:
    df["source_name"] = df["source_name"].fillna("(매체 미지정)")
    df["freq_date"] = pd.to_datetime(df["freq_date"])

    if period != "전체":
        days_map = {"최근 90일": 90, "최근 1년": 365, "최근 5년": 365 * 5}
        cutoff = df["freq_date"].max() - pd.Timedelta(days=days_map[period])
        df = df[df["freq_date"] >= cutoff]

    if agg == "주별":
        df["freq_date"] = df["freq_date"].dt.to_period("W").dt.start_time
        df = df.groupby(["freq_date", "source_name"], as_index=False)["count"].sum()
    elif agg == "월별":
        df["freq_date"] = df["freq_date"].dt.to_period("M").dt.start_time
        df = df.groupby(["freq_date", "source_name"], as_index=False)["count"].sum()

    fig = px.line(
        df,
        x="freq_date",
        y="count",
        color="source_name",
        markers=True,
        title=f'"{lemma}" 매체별 빈도 추이',
        labels={"freq_date": "날짜", "count": "빈도", "source_name": "매체"},
    )
    fig.update_layout(hovermode="x unified", height=450)
    trace_names = [tr.name for tr in fig.data]

    # 클릭 이벤트 받기 위해 on_select="rerun" 추가
    chart_event = st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"trend_{lemma}_{pos}",
        on_select="rerun",
        selection_mode="points",
    )
    st.caption(
        "오른쪽 '매체' 범례를 클릭하면 특정 매체만 켜고 끌 수 있습니다. "
        "그래프의 한 점을 클릭하면 그 시점·매체의 용례 20건을 아래에 띄웁니다."
    )

    # ---------- 시계열 클릭 → 용례 표시 ----------

    # source_name → source_id 매핑 (curveNumber는 그래프상 선의 인덱스)
    # px.line은 color 그룹 알파벳순으로 trace 만듦 → df에서 unique한 source_name 순서로 매핑
    source_names_in_order = trace_names

    @st.cache_data(ttl=300)
    def fetch_source_id_by_name(source_name: str) -> int | None:
        if source_name == "(매체 미지정)":
            return None
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT source_id FROM sources WHERE name = %s", (source_name,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None

    def get_date_range(clicked_date: pd.Timestamp, agg: str) -> tuple[pd.Timestamp, pd.Timestamp]:
        """집계 단위에 따라 클릭된 시점의 시작·끝 날짜를 반환"""
        if agg == "일별":
            return clicked_date, clicked_date
        elif agg == "주별":
            # 클릭된 날짜는 주의 시작일 (월요일)
            return clicked_date, clicked_date + pd.Timedelta(days=6)
        else:  # 월별
            start = clicked_date.replace(day=1)
            # 다음 달 1일 - 1일
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1) - pd.Timedelta(days=1)
            else:
                end = start.replace(month=start.month + 1) - pd.Timedelta(days=1)
            return start, end

    @st.cache_data(ttl=120)
    def fetch_examples_at_point(
        lemma: str,
        pos: str,
        source_id: int | None,
        date_start: pd.Timestamp,
        date_end: pd.Timestamp,
        limit: int = 20,
    ):
        """segment_lemma_map 기반 — 해당 lemma가 등장한 세그먼트만 가져옴."""
        conn = get_conn()
        cur = conn.cursor()
        date_start_s = date_start.strftime("%Y-%m-%d")
        date_end_s = date_end.strftime("%Y-%m-%d")
        pos_list = expand_pos(pos)

        if source_id == 7:
            cur.execute("""
                SELECT e.embedding_id, e.segment_text,
                       c.published_at, NULL::text, NULL::text
                FROM segment_lemma_map m
                JOIN embeddings e ON m.embedding_id = e.embedding_id
                JOIN comments c ON e.comment_id = c.comment_id
                WHERE m.lemma = %s AND m.pos = ANY(%s)
                  AND c.published_at::date BETWEEN %s AND %s
                ORDER BY c.published_at DESC
                LIMIT %s
            """, (lemma, pos_list, date_start_s, date_end_s, limit))
        elif source_id is None:
            cur.execute("""
                SELECT e.embedding_id, e.segment_text,
                       t.published_at, NULL::text, NULL::text
                FROM segment_lemma_map m
                JOIN embeddings e ON m.embedding_id = e.embedding_id
                JOIN texts t ON e.text_id = t.text_id
                WHERE m.lemma = %s AND m.pos = ANY(%s)
                  AND t.source_id IS NULL
                  AND t.published_at::date BETWEEN %s AND %s
                ORDER BY t.published_at DESC
                LIMIT %s
            """, (lemma, pos_list, date_start_s, date_end_s, limit))
        else:
            cur.execute("""
                SELECT e.embedding_id, e.segment_text,
                       t.published_at, NULL::text, NULL::text
                FROM segment_lemma_map m
                JOIN embeddings e ON m.embedding_id = e.embedding_id
                JOIN texts t ON e.text_id = t.text_id
                WHERE m.lemma = %s AND m.pos = ANY(%s)
                  AND t.source_id = %s
                  AND t.published_at::date BETWEEN %s AND %s
                ORDER BY t.published_at DESC
                LIMIT %s
            """, (lemma, pos_list, source_id, date_start_s, date_end_s, limit))

        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    def bold_lemma_in_text(text: str, lemma: str, pos: str) -> str:
        """동사·형용사는 어간 + 활용형(최대 5글자)까지 bold. 명사 등은 단순 치환."""
        if pos in ("VV", "VA"):
            stem = lemma[:-1] if lemma.endswith("다") else lemma
            if not stem:
                return text
            pattern = re.compile(re.escape(stem) + r"[가-힣]{0,5}")
            return pattern.sub(lambda m: f"**{m.group(0)}**", text)
        else:
            return text.replace(lemma, f"**{lemma}**")

    def render_point_example(row, lemma: str, pos: str):
        item_id, content, published_at, title, url = row
        if not content:
            return
        display = bold_lemma_in_text(content, lemma, pos)
        preview = display[:200] + ("..." if len(display) > 200 else "")
        meta = []
        if published_at: meta.append(str(published_at)[:10])
        if title: meta.append(f"제목: {title}")
        if url: meta.append(f"[원문 링크]({url})")
        with st.expander(preview, expanded=False):
            st.markdown(display)
            if meta: st.caption(" · ".join(meta))

    selected_points = chart_event.selection.get("points", []) if chart_event else []

    if selected_points:
        pt = selected_points[0]  # 첫 클릭만 처리
        curve_idx = pt.get("curve_number")
        clicked_x = pt.get("x")

        if curve_idx is not None and clicked_x is not None and curve_idx < len(source_names_in_order):
            source_name = source_names_in_order[curve_idx]
            clicked_date = pd.to_datetime(clicked_x)
            date_start, date_end = get_date_range(clicked_date, agg)
            source_id = fetch_source_id_by_name(source_name)

            range_label = (
                date_start.strftime("%Y-%m-%d")
                if date_start == date_end
                else f"{date_start.strftime('%Y-%m-%d')} ~ {date_end.strftime('%Y-%m-%d')}"
            )

            st.markdown(f"#### 🎯 클릭된 시점 용례 — {source_name} · {range_label}")

            examples = fetch_examples_at_point(lemma, pos, source_id, date_start, date_end)

            if not examples:
                st.info("이 시점·매체에 매칭된 용례가 없어요. (morphemes에 없음)")
            else:
                st.caption(f"최신순 {len(examples)}건 (최대 20건)")
                for row in examples:
                    render_point_example(row, lemma, pos)

st.divider()

# ---------- AI 분석 바로가기 ----------
st.markdown("### 🤖 AI 의미 분석")
st.caption("클러스터링과 Claude 검증으로 이 단어의 의미를 자동 분석할 수 있습니다.")

col1, col2 = st.columns([3, 1])
with col1:
    st.info("더 상세한 의미 분석(클러스터링 + Claude 검증)은 별도 페이지에서 확인하세요.")
with col2:
    if st.button("🚀 AI 분석 페이지로", use_container_width=True, type="primary"):
        st.query_params["word"] = lemma
        st.switch_page("pages/5_AI_의미_분석.py")
