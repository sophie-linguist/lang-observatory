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


def expand_pos(pos: str) -> list[str]:
    """'NNG·NNP' 같은 합쳐진 pos를 리스트로 펼침."""
    return pos.split("·") if "·" in pos else [pos]

st.set_page_config(page_title="어휘 의미 탐색", layout="wide")

import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/dashboard")
from auth import check_password
check_password()

st.title("어휘 의미 탐색")

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
</style>
""", unsafe_allow_html=True)

# 고급스러운 돋보기 SVG 타이틀 레이아웃 생성


# ---------- 검색창 ----------
default_query = st.query_params.get("word", "")

query = st.text_input(
    "검색어",
    value=default_query,
    placeholder="예: 긁다, 헬스",
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
    st.info("검색창에 단어를 입력하세요.")
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

    cur.close()
    conn.close()
    return freq_rows, dict_rows, cand_rows


freq_rows, dict_rows, cand_rows = fetch_basic_info(lemma, pos)

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

    for idx, (sn, p, definition, examples, sense_cat, link) in enumerate(senses, 1):
        label_num = idx if dict_source == "stdict" else sn
        header = f"**{label_num}.** {definition}"
        if dict_source == "stdict":
            header += f" &nbsp; `sense_code {sn}`"

        with st.expander(header, expanded=False):
            meta = []
            if p: meta.append(f"품사 `{p}`")
            if sense_cat: meta.append(f"범주 `{sense_cat}`")
            if meta: st.caption(" · ".join(meta))

            if examples:
                st.markdown("**예문**")
                for ex in examples:
                    st.markdown(render_example(ex))
            else:
                st.caption("예문 없음")

            if link:
                st.caption(f"[원문 링크]({link})")


st.divider()

# ---------- 사전 등재 ----------
st.markdown("#### 📖 사전 정보")
if not dict_rows:
    st.markdown(":red[미등재] (세 사전 어디에도 없음)")
else:
    dict_label = {
        "urimalsaem": "우리말샘",
        "stdict": "표준국어대사전",
        "kbd": "한국어기초사전",
    }
    by_source = {ds: cnt for ds, cnt in dict_rows}
    available_dicts = [s for s in ["urimalsaem", "stdict", "kbd"] if s in by_source]
    missing_dicts = [s for s in ["urimalsaem", "stdict", "kbd"] if s not in by_source]

    if missing_dicts:
        missing_str = " · ".join(dict_label[s] for s in missing_dicts)
        st.caption(f":red[미등재]: {missing_str}")

    tab_labels = [f"{dict_label[s]} ({by_source[s]}개 sense)" for s in available_dicts]
    tabs = st.tabs(tab_labels)
    for tab, src in zip(tabs, available_dicts):
        with tab:
            render_dict_senses(lemma, src)

st.divider()

# 신어 후보
st.markdown("#### 🆕 신어 후보 등록 여부")
if not cand_rows:
    st.markdown("등록되지 않음")
else:
    for cid, p, status, detected_at in cand_rows:
        st.markdown(
            f"- candidate_id `{cid}` · 품사 `{p}` · 상태 `{status}` · 첫 발견 {detected_at}"
        )

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

# ---------- 클러스터 + 대표 용례 ----------
st.markdown("### 🧬 의미 클러스터 결과 (매체별)")
st.caption("매체별로 임베딩 결과를 HDBSCAN 방식으로 클러스터링한 결과입니다.")

@st.cache_data(ttl=60)
def fetch_clusters_by_source(lemma: str, pos: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            uc.cluster_id,
            uc.source_id,
            s.name AS source_name,
            uc.member_count,
            uc.cluster_label
        FROM usage_clusters uc
        LEFT JOIN sources s ON s.source_id = uc.source_id
        WHERE uc.lemma = %s AND uc.pos = ANY(%s)
        ORDER BY uc.source_id, uc.member_count DESC
    """, (lemma, expand_pos(pos)))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@st.cache_data(ttl=60)
def fetch_cluster_examples(cluster_id: int, lemma: str, limit: int = 3):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            ucm.similarity,
            e.text_id,
            e.comment_id,
            e.segment_text AS content,
            COALESCE(t.published_at, c.published_at) AS published_at,
            t.title,
            t.url
        FROM usage_cluster_members ucm
        JOIN embeddings e ON e.embedding_id = ucm.embedding_id
        LEFT JOIN texts t ON t.text_id = e.text_id
        LEFT JOIN comments c ON c.comment_id = e.comment_id
        WHERE ucm.cluster_id = %s
        ORDER BY ucm.similarity DESC NULLS LAST
        LIMIT %s
    """, (cluster_id, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def render_cluster_example(ex, lemma: str):
    similarity, text_id, comment_id, content, published_at, title, url = ex
    if not content:
        return

    display_content = content.replace("\n", " ").replace(lemma, f"**{lemma}**")

    if len(display_content) > 200:
        preview = display_content[:200] + "..."
        with st.expander(preview, expanded=False):
            st.markdown(display_content)
            meta = []
            if published_at: meta.append(str(published_at)[:10])
            if similarity is not None: meta.append(f"유사도 {similarity:.3f}")
            if meta: st.caption(" · ".join(meta))
    else:
        st.markdown(f"- {display_content}")
        meta_parts = []
        if published_at: meta_parts.append(str(published_at)[:10])
        if similarity is not None: meta_parts.append(f"유사도 {similarity:.3f}")
        if meta_parts: st.caption("  " + " · ".join(meta_parts))

@st.cache_data(ttl=60)
def fetch_validations(lemma: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT validation_id, pos, n_clusters, n_examples, judgment,
               claude_result, created_at
        FROM sense_validation
        WHERE headword = %s
        ORDER BY created_at DESC
    """, (lemma,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


@st.cache_data(ttl=60)
def fetch_cluster_source_map(cluster_ids_tuple):
    cluster_ids = list(cluster_ids_tuple)
    if not cluster_ids:
        return {}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT uc.cluster_id, s.name
        FROM usage_clusters uc
        LEFT JOIN sources s ON s.source_id = uc.source_id
        WHERE uc.cluster_id = ANY(%s)
    """, (cluster_ids,))
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return result


def render_validation_card(v, source_map):
    validation_id, pos, n_clusters, n_examples, judgment, claude_result, created_at = v

    if isinstance(claude_result, str):
        claude_result = json.loads(claude_result)

    senses = claude_result.get("senses", [])
    context_distribution = claude_result.get("context_distribution", [])
    notes = claude_result.get("notes", "")

    all_cluster_ids = set()
    for s in senses:
        all_cluster_ids.update(s.get("cluster_ids_merged", []))
    for cd in context_distribution:
        all_cluster_ids.update(cd.get("cluster_ids", []))

    source_labels = sorted({source_map.get(cid) for cid in all_cluster_ids if source_map.get(cid)})
    source_str = " · ".join(source_labels) if source_labels else "(매체 추적 불가)"

    st.markdown(f"#### 검증 #{validation_id} — {created_at.strftime('%Y-%m-%d %H:%M')} · {source_str}")
    st.markdown(f"**판정**: `{judgment}` · `{pos}` · {n_clusters} 클러스터 · {n_examples} 용례")

    for s in senses:
        sense_no = s.get("sense_no", "?")
        definition = s.get("definition", "")
        rep_ex = s.get("representative_example", "")
        cluster_ids_merged = s.get("cluster_ids_merged", [])
        syntax = s.get("syntax_info", {})

        cluster_str = f"클러스터 {', '.join(map(str, cluster_ids_merged))}" if cluster_ids_merged else ""
        st.markdown(f"##### 의미 {sense_no} · {cluster_str}")
        st.markdown(f"**{definition}**")
        if rep_ex:
            st.markdown(f"> {rep_ex}")

        dict_matches = s.get("dict_sense_matches", {})
        if dict_matches:
            match_parts = []
            dict_short = {"urimalsaem": "우", "stdict": "표", "kbd": "기"}
            for src in ["urimalsaem", "stdict", "kbd"]:
                val = dict_matches.get(src)
                if val is not None:
                    match_parts.append(f"{dict_short[src]} {val}")
                else:
                    match_parts.append(f"{dict_short[src]} 신의미")
            st.caption(f"사전 매칭: {' · '.join(match_parts)}")

        perspectives = s.get("perspectives_used", [])
        if perspectives:
            st.caption(f"적용 관점: {' · '.join(perspectives)}")

        if syntax:
            with st.expander("문법 정보 (collocates, argument structure 등)"):
                arg = syntax.get("argument_structure")
                if arg: st.markdown(f"**구조**: `{arg}`")
                colls = syntax.get("collocates", [])
                if colls: st.markdown(f"**공기어**: {', '.join(colls)}")
                mods = syntax.get("common_modifiers", [])
                if mods: st.markdown(f"**자주 같이 쓰이는 수식어**: {', '.join(mods)}")
                pre = syntax.get("preceding_patterns", [])
                if pre: st.markdown(f"**앞 패턴**: {', '.join(pre)}")
                fol = syntax.get("following_patterns", [])
                if fol: st.markdown(f"**뒤 패턴**: {', '.join(fol)}")

    if context_distribution:
        st.markdown("##### 📊 맥락 분포")
        for cd in context_distribution:
            label = cd.get("context_label", "")
            prop = cd.get("proportion", 0)
            desc = cd.get("description", "")
            cluster_ids = cd.get("cluster_ids", [])
            cluster_str = f"클러스터 {', '.join(map(str, cluster_ids))}" if cluster_ids else ""
            st.markdown(f"- **{label}** ({prop:.0%}) — {cluster_str}")
            if desc: st.caption(f"  {desc}")

    diagnostics = claude_result.get("system_diagnostics", {})
    if diagnostics and any(diagnostics.values()):
        with st.expander("⚠️ 시스템 한계 자기 진단"):
            for key, label in [
                ("clustering_quality", "클러스터링 품질"),
                ("headword_presence_note", "표제어 부재 비율"),
                ("corpus_limitations", "코퍼스 한계"),
                ("embedding_limitations", "임베딩 한계"),
            ]:
                val = diagnostics.get(key)
                if val: st.markdown(f"**{label}**: {val}")

    if notes:
        with st.expander("📝 Claude 분석 메모"):
            st.markdown(notes)

    st.markdown("---")


def trigger_validation(lemma: str, pos: str, source_id: int, status_placeholder):
    from analyzers.cluster_usage import run_cluster
    from analyzers.claude_analyzer import (
        fetch_word_data, build_prompt, call_claude, save_to_db,
    )
    from db import get_conn

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM usage_clusters
        WHERE lemma = %s AND pos = %s AND source_id = %s
    """, (lemma, pos, source_id))
    cluster_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    if cluster_count == 0:
        status_placeholder.write("🔬 클러스터링 중... (1~5분, 용례 양에 따라)")
        result = run_cluster(lemma, pos, source_id)
        status_placeholder.write(f"  → 클러스터링 결과: {result.get('status')}")
        if result.get('status') != 'success':
            return None
    else:
        status_placeholder.write(f"✓ 클러스터 {cluster_count}개 이미 있음 — 검증으로 바로 진행")

    status_placeholder.write("📊 검증용 데이터 모으는 중...")
    data = fetch_word_data(lemma, pos, source_id=source_id)
    if data is None:
        return None
    status_placeholder.write(f"  → 클러스터 {len(data['clusters'])}개, 세 사전 sense {len(data['dict_senses'])}개")

    status_placeholder.write("🤖 Claude 호출 중... (1~3분)")
    prompt = build_prompt(data)
    result = call_claude(prompt)
    if result is None:
        return None

    status_placeholder.write("💾 DB 저장 중...")
    validation_id = save_to_db(lemma, data, result)
    return validation_id


def render_trigger_buttons(lemma: str, pos: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.source_id, s.name, COUNT(DISTINCT m.text_id) AS n
        FROM morphemes m
        JOIN texts t ON m.text_id = t.text_id
        JOIN sources s ON s.source_id = t.source_id
        WHERE m.lemma = %s AND m.pos = ANY(%s)
          AND m.text_id IS NOT NULL
        GROUP BY s.source_id, s.name
        HAVING COUNT(DISTINCT m.text_id) >= 30
    """, (lemma, expand_pos(pos)))
    text_sources = cur.fetchall()

    cur.execute("""
        SELECT 7 AS source_id, '유튜브 댓글' AS name, COUNT(DISTINCT comment_id) AS n
        FROM morphemes
        WHERE lemma = %s AND pos = ANY(%s)
          AND comment_id IS NOT NULL
        HAVING COUNT(DISTINCT comment_id) >= 30
    """, (lemma, expand_pos(pos)))

    comment_sources = cur.fetchall()

    cur.close()
    conn.close()

    all_sources = list(text_sources) + list(comment_sources)

    if not all_sources:
        st.caption("이 단어는 클러스터링/검증할 만큼의 용례가 없어요 (매체별 30건 미만).")
        return

    st.markdown("##### 🚀 새로 검증하기")
    st.caption("클러스터링 + Claude 검증을 한 번에 진행합니다 (매체별 분리, 5~10분 소요).")

    cols = st.columns(len(all_sources))
    for col, (sid, name, n) in zip(cols, all_sources):
        with col:
            button_label = f"🚀 {name} ({n}건)"
            if st.button(button_label, key=f"trigger_{lemma}_{pos}_{sid}", use_container_width=True):
                status = st.status(f"검증 진행 중: {lemma}/{pos} × {name}", expanded=True)
                with status:
                    placeholder = st.empty()
                    validation_id = trigger_validation(lemma, pos, sid, placeholder)
                    if validation_id:
                        placeholder.write(f"✅ 완료. validation_id={validation_id}")
                        status.update(label=f"✅ 완료: {lemma}/{pos} × {name}", state="complete")
                        st.success("검증 완료! 페이지를 새로고침하면 결과가 보입니다.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        placeholder.write("❌ 실패")
                        status.update(label=f"❌ 실패: {lemma}/{pos} × {name}", state="error")


clusters = fetch_clusters_by_source(lemma, pos)

if not clusters:
    st.info(
        f"'{lemma}' ({pos})에 대한 클러스터링 결과가 아직 없어요. "
        "검증 페이지에서 트리거하거나, 터미널에서 "
        "`python3 src/cluster_usage.py {lemma} {pos} {source_id}` 돌리면 여기에 떠요."
    )
else:
    by_source = defaultdict(list)
    for c in clusters:
        by_source[(c[1], c[2])].append(c)

    tab_labels = [
        f"{name or '(매체 미지정)'} ({len(cs)} 클러스터, {sum(c[3] for c in cs):,} 용례)"
        for (sid, name), cs in by_source.items()
    ]
    tabs = st.tabs(tab_labels)

    for tab, ((sid, name), cs) in zip(tabs, by_source.items()):
        with tab:
            for c in cs:
                cluster_id, src_id, src_name, member_count, label = c
                header = f"**클러스터 {cluster_id}** — {member_count:,}건"
                if label:
                    header += f" · {label}"
                st.markdown(header)

                examples = fetch_cluster_examples(cluster_id, lemma, limit=3)
                if not examples:
                    st.caption("대표 용례 없음")
                else:
                    for ex in examples:
                        render_cluster_example(ex, lemma)
                st.markdown("---")

st.divider()

# ---------- 검증 결과 ----------
st.markdown("### 🔬 의미 클러스터 검증 결과")

validations = fetch_validations(lemma)

if not validations:
    st.info("이 단어에 대한 검증 이력이 없어요.")
    render_trigger_buttons(lemma, pos)
else:
    all_cluster_ids = set()
    for v in validations:
        claude_result = v[5]
        if isinstance(claude_result, str):
            claude_result = json.loads(claude_result)
        for s in claude_result.get("senses", []):
            all_cluster_ids.update(s.get("cluster_ids_merged", []))
        for cd in claude_result.get("context_distribution", []):
            all_cluster_ids.update(cd.get("cluster_ids", []))

    source_map = fetch_cluster_source_map(tuple(sorted(all_cluster_ids)))

    st.caption(f"Claude로 검증한 총 {len(validations)}건의 이력 (최근 순)")
    for v in validations:
        render_validation_card(v, source_map)

    st.markdown("---")
    render_trigger_buttons(lemma, pos)
