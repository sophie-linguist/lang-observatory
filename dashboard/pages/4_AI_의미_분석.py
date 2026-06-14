import streamlit as st
import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/src")
from db import get_conn
import json
import pandas as pd
import re
from collections import defaultdict
import html


def expand_pos(pos: str) -> list[str]:
    """'NNG·NNP' 같은 합쳐진 pos를 리스트로 펼침."""
    return pos.split("·") if "·" in pos else [pos]

st.set_page_config(page_title="AI 의미 분석", layout="wide")

sys.path.insert(0, "/home/ssohe/lang-observatory/dashboard")
from auth import check_password
check_password()

# 분석 진행 중일 때 페이지 이탈 경고
if st.session_state.get('analysis_running', False):
    # 경고 배너 표시
    st.markdown("""<div style='background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 16px 24px; border-radius: 12px; color: white; margin-bottom: 16px; border: 2px solid #b91c1c; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);'>
    <div style='font-size: 18px; font-weight: 700; margin-bottom: 4px;'>⚠️ 분석 진행 중 - 페이지를 이동하지 마세요!</div>
    <div style='font-size: 14px; opacity: 0.95;'>페이지를 이동하면 분석 작업이 중단됩니다. 완료될 때까지 기다려주세요.</div>
    </div>""", unsafe_allow_html=True)

    # JavaScript로 페이지 이탈 방지
    st.components.v1.html("""
    <script>
    // 브라우저 탭 닫기/외부 이동 방지
    window.onbeforeunload = function(e) {
        e.preventDefault();
        e.returnValue = '';
        return '분석이 진행 중입니다. 페이지를 떠나면 작업이 중단됩니다.';
    };

    // Streamlit 내부 페이지 전환 방지
    function attachWarnings() {
        const allLinks = window.parent.document.querySelectorAll('a');

        allLinks.forEach(link => {
            if (link.dataset.warningAttached) return;
            link.dataset.warningAttached = 'true';

            ['mousedown', 'click', 'mouseup'].forEach(function(eventType) {
                link.addEventListener(eventType, function(e) {
                    const href = this.getAttribute('href');
                    if (href && (href.startsWith('/') || href.includes('localhost') || href.includes('lang-observatory.com'))) {
                        if (!confirm('⚠️ 분석이 진행 중입니다!\\n\\n페이지를 이동하면 작업이 중단됩니다.\\n\\n정말 이동하시겠습니까?')) {
                            e.preventDefault();
                            e.stopPropagation();
                            e.stopImmediatePropagation();
                            return false;
                        }
                    }
                }, true);
            });
        });
    }

    // 초기 실행 및 동적 링크 감지
    setTimeout(attachWarnings, 100);
    setTimeout(attachWarnings, 500);
    setTimeout(attachWarnings, 1000);

    const observer = new MutationObserver(attachWarnings);
    setTimeout(function() {
        observer.observe(window.parent.document.body, {
            childList: true,
            subtree: true
        });
    }, 100);
    </script>
    """, height=0)

st.markdown("""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 16px; color: white; margin-bottom: 24px;'>
<div style='font-size: 28px; font-weight: 700; margin-bottom: 8px;'>🤖 AI 의미 분석</div>
<div style='font-size: 16px; opacity: 0.95;'>클러스터링과 Claude 검증으로 단어의 의미를 자동 분석합니다</div>
</div>""", unsafe_allow_html=True)

st.markdown("""
<style>
/* 1. 세련된 웹 폰트(Pretendard) 로드 및 앱 전체 적용 */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}

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

/* 버튼 기본 스타일 */
div[data-testid="stButton"] > button {
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    color: #475569 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    transition: all 0.2s ease !important;
    min-width: 120px !important;
}
div[data-testid="stButton"] > button:hover {
    background-color: #F1F5F9 !important;
    border-color: #CBD5E1 !important;
    color: #0F172A !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
}

/* Primary 버튼 스타일 */
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stButton"] > button[data-baseweb="button"][kind="primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #5568d3 0%, #6a3f8f 100%) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3) !important;
}

/* Popover 버튼 (더 작게) */
div[data-testid="stPopover"] > button {
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    color: #475569 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 8px 14px !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stPopover"] > button:hover {
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

/* Dataframe 테이블 → 프리미엄 디자인 */
[data-testid="stDataFrame"] {
    border: 2px solid #E2E8F0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
}
[data-testid="stDataFrame"] thead {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
}
[data-testid="stDataFrame"] thead th {
    color: white !important;
    font-weight: 600 !important;
    padding: 14px 16px !important;
    font-size: 14px !important;
    letter-spacing: 0.3px !important;
}
[data-testid="stDataFrame"] tbody td {
    padding: 12px 16px !important;
    font-size: 14px !important;
    border-bottom: 1px solid #F1F5F9 !important;
}
[data-testid="stDataFrame"] tbody tr {
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}
[data-testid="stDataFrame"] tbody tr:hover {
    background: linear-gradient(90deg, #F8FAFC 0%, #EEF2FF 100%) !important;
    transform: scale(1.01) !important;
}
/* 선택된 행 강조 */
[data-testid="stDataFrame"] tbody tr[aria-selected="true"] {
    background: linear-gradient(90deg, #E0E7FF 0%, #DDD6FE 100%) !important;
    border-left: 4px solid #667eea !important;
    font-weight: 600 !important;
}
[data-testid="stDataFrame"] tbody tr[aria-selected="true"] td {
    color: #1E293B !important;
}

/* Metric 카드 디자인 */
[data-testid="stMetric"] {
    background-color: #F8FAFC !important;
    padding: 16px !important;
    border-radius: 10px !important;
    border: 1px solid #E2E8F0 !important;
}

/* Checkbox → 카드 스타일 */
[data-testid="stCheckbox"] {
    background: white !important;
    border: 2px solid #E2E8F0 !important;
    border-radius: 10px !important;
    padding: 12px 16px !important;
    transition: all 0.2s ease !important;
    margin: 6px 0 !important;
}
[data-testid="stCheckbox"]:hover {
    border-color: #667eea !important;
    background: #F8FAFC !important;
    transform: translateX(4px) !important;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1) !important;
}
[data-testid="stCheckbox"] label {
    cursor: pointer !important;
    font-weight: 500 !important;
}
[data-testid="stCheckbox"] input[type="checkbox"]:checked ~ label {
    color: #667eea !important;
    font-weight: 600 !important;
}
/* 체크박스 자체 스타일 */
[data-testid="stCheckbox"] input[type="checkbox"] {
    width: 20px !important;
    height: 20px !important;
    border: 2px solid #CBD5E1 !important;
    border-radius: 6px !important;
}
[data-testid="stCheckbox"] input[type="checkbox"]:checked {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border-color: #667eea !important;
}

/* Progress bar 디자인 */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
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


# ---------- 검색창 ----------
default_query = st.query_params.get("word", "")

query = st.text_input(
    "분석할 단어 검색",
    value=default_query,
    placeholder="단어를 입력하세요",
    help="2글자 이상 입력하면 전방 일치로 후보를 보여줍니다.",
)


# ---------- 부분 일치 후보 조회 ----------
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
    st.markdown("""<div style='background: white; border: 2px solid #E2E8F0; border-radius: 16px; padding: 32px; margin: 24px 0; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);'>
<div style='text-align: center; margin-bottom: 32px;'>
<div style='font-size: 48px; margin-bottom: 12px;'>🤖</div>
<div style='font-size: 24px; font-weight: 700; color: #1E293B; margin-bottom: 8px;'>AI 의미 분석</div>
<div style='font-size: 15px; color: #64748b;'>클러스터링과 Claude API를 활용한 자동 의미 분석 시스템</div>
</div>
<div style='margin-bottom: 28px;'>
<div style='font-size: 18px; font-weight: 600; color: #334155; margin-bottom: 16px; padding-left: 12px; border-left: 4px solid #667eea;'>주요 기능</div>
<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px;'>
<div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border: 1px solid #E2E8F0;'>
<div style='font-size: 20px; margin-bottom: 6px;'>🧬</div>
<div style='font-size: 15px; font-weight: 600; color: #334155; margin-bottom: 4px;'>의미 클러스터링</div>
<div style='font-size: 13px; color: #64748b; line-height: 1.4;'>임베딩 기반 자동 의미 분류 (UMAP + HDBSCAN)</div>
</div>
<div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border: 1px solid #E2E8F0;'>
<div style='font-size: 20px; margin-bottom: 6px;'>🤖</div>
<div style='font-size: 15px; font-weight: 600; color: #334155; margin-bottom: 4px;'>Claude 검증</div>
<div style='font-size: 13px; color: #64748b; line-height: 1.4;'>AI가 클러스터를 분석하여 정의문 생성</div>
</div>
<div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border: 1px solid #E2E8F0;'>
<div style='font-size: 20px; margin-bottom: 6px;'>🚀</div>
<div style='font-size: 15px; font-weight: 600; color: #334155; margin-bottom: 4px;'>매체별 분석</div>
<div style='font-size: 13px; color: #64748b; line-height: 1.4;'>네이버 뉴스, 유튜브 댓글 등 매체 단위로 분리</div>
</div>
<div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border: 1px solid #E2E8F0;'>
<div style='font-size: 20px; margin-bottom: 6px;'>📊</div>
<div style='font-size: 15px; font-weight: 600; color: #334155; margin-bottom: 4px;'>검증 이력</div>
<div style='font-size: 13px; color: #64748b; line-height: 1.4;'>과거 분석 결과 조회 및 비교</div>
</div>
</div>
</div>
<div style='margin-bottom: 24px;'>
<div style='font-size: 18px; font-weight: 600; color: #334155; margin-bottom: 16px; padding-left: 12px; border-left: 4px solid #8b5cf6;'>분석 과정</div>
<div style='display: grid; gap: 10px;'>
<div style='background: linear-gradient(90deg, #F8FAFC 0%, white 100%); padding: 14px 18px; border-radius: 10px; border-left: 3px solid #667eea; display: flex; align-items: center; gap: 12px;'>
<div style='background: #667eea; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex-shrink: 0;'>1</div>
<div style='font-size: 14px; color: #334155;'><strong>단어 검색</strong> → 임베딩 세그먼트 확인</div>
</div>
<div style='background: linear-gradient(90deg, #F8FAFC 0%, white 100%); padding: 14px 18px; border-radius: 10px; border-left: 3px solid #8b5cf6; display: flex; align-items: center; gap: 12px;'>
<div style='background: #8b5cf6; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex-shrink: 0;'>2</div>
<div style='font-size: 14px; color: #334155;'><strong>매체 선택</strong> → 클러스터링 실행 (5~10분)</div>
</div>
<div style='background: linear-gradient(90deg, #F8FAFC 0%, white 100%); padding: 14px 18px; border-radius: 10px; border-left: 3px solid #6366f1; display: flex; align-items: center; gap: 12px;'>
<div style='background: #6366f1; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex-shrink: 0;'>3</div>
<div style='font-size: 14px; color: #334155;'><strong>Claude 분석</strong> → 의미 정의문 생성</div>
</div>
<div style='background: linear-gradient(90deg, #F8FAFC 0%, white 100%); padding: 14px 18px; border-radius: 10px; border-left: 3px solid #10b981; display: flex; align-items: center; gap: 12px;'>
<div style='background: #10b981; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex-shrink: 0;'>4</div>
<div style='font-size: 14px; color: #334155;'><strong>결과 저장</strong> → 탭에서 확인</div>
</div>
</div>
</div>
<div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); padding: 14px 18px; border-radius: 10px; margin-bottom: 12px; border-left: 4px solid #f59e0b;'>
<div style='font-size: 14px; color: #78350f; font-weight: 500;'>⚠️ 이 페이지는 비밀번호로 보호됩니다 (Claude API 비용 발생)</div>
</div>
<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 16px; border-radius: 12px; text-align: center;'>
<div style='font-size: 15px; color: white; font-weight: 500;'>👆 위 검색창에 단어를 입력하세요</div>
</div>
</div>""", unsafe_allow_html=True)
    st.stop()
else:
    df_cand = fetch_candidates(query)
    if df_cand.empty:
        st.warning(f"'{query}'(으)로 시작하는 단어가 없어요.")
        st.stop()

    st.markdown(f"### 분석할 단어 선택 (후보 {len(df_cand)}건)")

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
            "uri": st.column_config.NumberColumn("우리말샘", format="%d"),
            "std": st.column_config.NumberColumn("표준국어대", format="%d"),
            "kbd": st.column_config.NumberColumn("기초사전", format="%d"),
            "neo_status": st.column_config.TextColumn("신어 후보"),
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
    st.info("표에서 단어를 선택하면 아래에 AI 분석 결과가 떠요.")
    st.stop()

st.divider()
st.markdown(f"## 🤖 **{selected_lemma}** &nbsp;`{selected_pos}`")

lemma = selected_lemma
pos = selected_pos

# 임베딩 건수 조회
@st.cache_data(ttl=60)
def fetch_embedding_count(lemma: str, pos: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT m.embedding_id)
        FROM segment_lemma_map m
        WHERE m.lemma = %s AND m.pos = ANY(%s)
    """, (lemma, expand_pos(pos)))
    count = cur.fetchone()[0] if cur.rowcount > 0 else 0
    cur.close()
    conn.close()
    return count

embedding_count = fetch_embedding_count(lemma, pos)

# 임베딩 건수 표시
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown(f"### 📊 분석 대상 데이터")
    st.metric(
        label="임베딩 세그먼트 수",
        value=f"{embedding_count:,}건",
        help="이 단어가 포함된 300자 세그먼트 개수 (클러스터링 분석 대상)"
    )
    st.caption("💡 30건 이상일 때 클러스터링 + Claude 검증을 실행할 수 있습니다.")

with col2:
    # 빠른 통계
    st.markdown("##### 📈 빠른 통계")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM usage_clusters WHERE lemma = %s AND pos = ANY(%s)", (lemma, expand_pos(pos)))
    existing_clusters = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sense_validation WHERE headword = %s", (lemma,))
    existing_validations = cur.fetchone()[0]
    cur.close()
    conn.close()
    st.caption(f"기존 클러스터: {existing_clusters}개")
    st.caption(f"검증 이력: {existing_validations}건")

st.divider()

# ---------- 🚀 새로 검증하기 (위로 이동!) ----------
st.markdown("### 🚀 새로 검증하기")
st.caption("클러스터링 + Claude 검증을 동시에 진행할 매체를 선택하세요 (매체당 5~10분 소요)")

# 매체별 임베딩 건수 조회
@st.cache_data(ttl=60)
def fetch_available_sources(lemma: str, pos: str):
    conn = get_conn()
    cur = conn.cursor()

    # 텍스트 소스
    cur.execute("""
        SELECT s.source_id, s.name, COUNT(DISTINCT m.embedding_id) AS n
        FROM segment_lemma_map m
        JOIN embeddings e ON m.embedding_id = e.embedding_id
        JOIN texts t ON e.text_id = t.text_id
        JOIN sources s ON s.source_id = t.source_id
        WHERE m.lemma = %s AND m.pos = ANY(%s)
        GROUP BY s.source_id, s.name
        HAVING COUNT(DISTINCT m.embedding_id) >= 30
    """, (lemma, expand_pos(pos)))
    text_sources = cur.fetchall()

    # 유튜브 댓글
    cur.execute("""
        SELECT 7 AS source_id, '유튜브 댓글' AS name, COUNT(DISTINCT m.embedding_id) AS n
        FROM segment_lemma_map m
        JOIN embeddings e ON m.embedding_id = e.embedding_id
        WHERE m.lemma = %s AND m.pos = ANY(%s)
          AND e.comment_id IS NOT NULL
        HAVING COUNT(DISTINCT m.embedding_id) >= 30
    """, (lemma, expand_pos(pos)))
    comment_sources = cur.fetchall()

    cur.close()
    conn.close()

    return list(text_sources) + list(comment_sources)

available_sources = fetch_available_sources(lemma, pos)

if not available_sources:
    st.warning("⚠️ 이 단어는 클러스터링/검증할 만큼의 용례가 없어요 (매체별 30건 미만).")
else:
    # 세션 스테이트 초기화
    if 'selected_sources' not in st.session_state:
        st.session_state.selected_sources = set()

    st.markdown("**매체 선택:**")

    # 전체 선택/해제
    col_all, col_clear = st.columns(2)
    with col_all:
        if st.button("✅ 전체 선택", use_container_width=True):
            st.session_state.selected_sources = {src[0] for src in available_sources}
            st.rerun()
    with col_clear:
        if st.button("❌ 선택 해제", use_container_width=True):
            st.session_state.selected_sources = set()
            st.rerun()

    # 매체별 체크박스
    for source_id, source_name, count in available_sources:
        checkbox_key = f"src_{source_id}"
        checked = source_id in st.session_state.selected_sources

        if st.checkbox(
            f"{source_name} ({count:,}건)",
            value=checked,
            key=checkbox_key
        ):
            st.session_state.selected_sources.add(source_id)
        else:
            st.session_state.selected_sources.discard(source_id)

    # 실행 버튼
    selected_count = len(st.session_state.selected_sources)
    if selected_count > 0:
        button_label = f"🚀 선택한 {selected_count}개 매체 분석 시작"
        if st.button(button_label, type="primary", use_container_width=True):
            # 분석 시작 플래그 설정 + 선택한 매체/단어 저장 후 rerun
            st.session_state.analysis_running = True
            st.session_state.analysis_lemma = lemma
            st.session_state.analysis_pos = pos
            st.session_state.analysis_sources = [
                (sid, name, cnt) for sid, name, cnt in available_sources
                if sid in st.session_state.selected_sources
            ]
            st.rerun()

# 분석 실행 (rerun 후)
if st.session_state.get('analysis_running', False) and st.session_state.get('analysis_sources'):
    # session_state에서 단어 정보 가져오기
    lemma = st.session_state.get('analysis_lemma')
    pos = st.session_state.get('analysis_pos')

    if lemma and pos:
        selected_sources_list = st.session_state.analysis_sources

        st.markdown("---")
        st.markdown("### 🔄 분석 진행 중...")

        progress_bar = st.progress(0)
        total = len(selected_sources_list)

        for idx, (source_id, source_name, _) in enumerate(selected_sources_list):
            with st.status(f"📊 {source_name} 분석 중...", expanded=True) as status:
                placeholder = st.empty()

                from analyzers.cluster_usage import run_cluster
                from analyzers.claude_analyzer import (
                    fetch_word_data, build_prompt, call_claude, save_to_db,
                )

                # 클러스터 확인
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) FROM usage_clusters
                    WHERE lemma = %s AND pos = %s AND source_id = %s
                """, (lemma, pos, source_id))
                cluster_count = cur.fetchone()[0]
                cur.close()
                conn.close()

                # 클러스터링
                if cluster_count == 0:
                    placeholder.write("🔬 클러스터링 중... (1~5분)")
                    result = run_cluster(lemma, pos, source_id)
                    if result.get('status') != 'success':
                        placeholder.write(f"❌ 클러스터링 실패: {result.get('message')}")
                        status.update(label=f"❌ {source_name} 실패", state="error")
                        continue
                    placeholder.write(f"✓ 클러스터링 완료")
                else:
                    placeholder.write(f"✓ 클러스터 {cluster_count}개 이미 있음")

                # Claude 검증
                placeholder.write("📊 검증용 데이터 수집 중...")
                data = fetch_word_data(lemma, pos, source_id=source_id)
                if data is None:
                    placeholder.write("❌ 데이터 수집 실패")
                    status.update(label=f"❌ {source_name} 실패", state="error")
                    continue

                placeholder.write("🤖 Claude 호출 중... (1~3분)")
                prompt = build_prompt(data)
                result = call_claude(prompt)
                if result is None:
                    placeholder.write("❌ Claude 호출 실패")
                    status.update(label=f"❌ {source_name} 실패", state="error")
                    continue

                placeholder.write("💾 DB 저장 중...")
                validation_id = save_to_db(lemma, data, result)

                placeholder.write(f"✅ 완료! validation_id={validation_id}")
                status.update(label=f"✅ {source_name} 완료", state="complete")

            # 진행률 업데이트
            progress_bar.progress((idx + 1) / total)

        st.success(f"🎉 {len(selected_sources_list)}개 매체 분석 완료! 아래 탭에서 결과를 확인하세요.")
        # 분석 완료 - 모든 플래그 초기화
        st.session_state.selected_sources = set()
        st.session_state.analysis_running = False
        st.session_state.analysis_sources = None
        st.session_state.analysis_lemma = None
        st.session_state.analysis_pos = None
        st.cache_data.clear()
        st.rerun()

st.divider()

# ---------- 함수 정의 ----------
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

    # 헤더: 매체와 메타 정보를 명확히
    header_html = f"""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 16px; border-radius: 12px 12px 0 0; color: white;'>
<div style='font-size: 18px; font-weight: 600; margin-bottom: 8px;'>
검증 #{validation_id} · {judgment}
</div>
<div style='font-size: 14px; opacity: 0.9;'>
📊 {source_str} | ⏰ {created_at.strftime('%Y-%m-%d %H:%M')}
</div>
<div style='font-size: 13px; opacity: 0.85; margin-top: 4px;'>
{n_clusters}개 클러스터 통합 · {n_examples or '?'}개 용례 분석 · {len(senses)}개 의미 발견
</div>
</div>"""

    st.markdown(header_html, unsafe_allow_html=True)

    # 의미 정렬: 신의미를 먼저 표시
    def sort_key(sense):
        dict_matches = sense.get("dict_sense_matches", {})
        # 사전에 하나라도 매칭되면 기존 의미
        is_existing = any(v is not None for v in dict_matches.values()) if dict_matches else False
        # 신의미(False)가 먼저 오도록 is_existing을 키로 사용
        return (is_existing, sense.get("sense_no", 999))

    sorted_senses = sorted(senses, key=sort_key)

    # 의미별 카드
    for s in sorted_senses:
        sense_no = s.get("sense_no", "?")
        definition = s.get("definition", "")
        sense_type = s.get("type", "")
        rep_ex = s.get("representative_example", "")
        cluster_ids_merged = s.get("cluster_ids_merged", [])
        syntax = s.get("syntax_info", {})
        dict_matches = s.get("dict_sense_matches", {})
        perspectives = s.get("perspectives_used", [])

        # 사전 매칭 상태 계산
        dict_short = {"urimalsaem": "우", "stdict": "표", "kbd": "기"}
        dict_badges = []
        is_new_sense = True
        if dict_matches:
            for src in ["urimalsaem", "stdict", "kbd"]:
                val = dict_matches.get(src)
                if val is not None:
                    dict_badges.append(f"<span style='background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;'>{dict_short[src]} {val}</span>")
                    is_new_sense = False
                else:
                    dict_badges.append(f"<span style='background: #f59e0b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;'>{dict_short[src]} 신의미</span>")

        new_badge = "<span style='background: #ef4444; color: white; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600;'>🆕 신의미</span>" if is_new_sense else ""

        # 클러스터 정보
        cluster_badge = ""
        if cluster_ids_merged:
            cluster_badge = f"<span style='background: #8b5cf6; color: white; padding: 4px 10px; border-radius: 6px; font-size: 12px;'>🧬 클러스터 {', '.join(map(str, cluster_ids_merged))} 통합</span>"

        # 관점 배지
        perspective_badges = ""
        if perspectives:
            perspective_badges = " ".join([f"<span style='background: #6366f1; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;'>{p}</span>" for p in perspectives])

        # HTML escape for safe rendering
        safe_definition = html.escape(definition) if definition else ""
        safe_rep_ex = html.escape(rep_ex) if rep_ex else ""

        html_content = f"""<div style='background: #f8fafc; border-left: 4px solid #667eea; padding: 20px; border-radius: 8px; margin: 16px 0;'>
<div style='margin-bottom: 12px;'>
<span style='font-size: 20px; font-weight: 700; color: #1e293b;'>의미 {sense_no}</span>
<span style='margin-left: 12px;'>{new_badge}</span>
<div style='margin-top: 8px;'>{cluster_badge}</div>
</div>
<div style='font-size: 18px; font-weight: 600; color: #334155; margin: 16px 0; line-height: 1.6;'>
{safe_definition}
</div>
{f"<div style='background: white; padding: 14px; border-radius: 6px; border-left: 3px solid #3b82f6; margin: 12px 0; font-style: italic; color: #475569;'>{safe_rep_ex}</div>" if safe_rep_ex else ""}
<div style='margin-top: 12px;'>
<div style='font-size: 13px; color: #64748b; margin-bottom: 6px;'>📚 사전 매칭:</div>
<div>{' '.join(dict_badges) if dict_badges else '<span style="color: #94a3b8;">매칭 정보 없음</span>'}</div>
</div>
{f"<div style='margin-top: 8px;'><span style='font-size: 12px; color: #64748b;'>🏷️ 적용 관점:</span> {perspective_badges}</div>" if perspectives else ""}
</div>"""

        st.markdown(html_content, unsafe_allow_html=True)

        # 결합 정보 카드
        if syntax:
            syntax_items = []
            arg = syntax.get("argument_structure")
            if arg:
                syntax_items.append(f"<div><span style='color: #64748b; font-weight: 600;'>논항 구조:</span> <code style='background: #f1f5f9; padding: 2px 6px; border-radius: 4px;'>{html.escape(arg)}</code></div>")

            for key, label, icon in [
                ("collocates", "공기어", "🔗"),
                ("common_modifiers", "수식어", "✏️"),
                ("preceding_patterns", "선행 패턴", "◀"),
                ("following_patterns", "후행 패턴", "▶"),
            ]:
                items = syntax.get(key, [])
                if items:
                    items_html = ", ".join([f"<span style='background: #e0e7ff; color: #4338ca; padding: 2px 6px; border-radius: 4px; font-size: 12px;'>{html.escape(it)}</span>" for it in items])
                    syntax_items.append(f"<div style='margin-top: 6px;'><span style='color: #64748b; font-weight: 600;'>{icon} {label}:</span> {items_html}</div>")

            if syntax_items:
                syntax_html = f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px; margin: 12px 0;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px;'>🔗 결합 정보</div>
{''.join(syntax_items)}
</div>"""
                st.markdown(syntax_html, unsafe_allow_html=True)

    # 맥락 분포 카드
    if context_distribution:
        context_items = []
        for cd in context_distribution:
            label = cd.get("context_label", "")
            prop = cd.get("proportion", 0)
            desc = cd.get("description", "")
            cluster_ids_ctx = cd.get("cluster_ids", [])
            cluster_str = f" · 클러스터 {', '.join(map(str, cluster_ids_ctx))}" if cluster_ids_ctx else ""

            context_items.append(f"""<div style='background: #f8fafc; padding: 12px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #6366f1;'>
<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;'>
<span style='font-size: 14px; font-weight: 600; color: #334155;'>{html.escape(label)}</span>
<span style='background: #6366f1; color: white; padding: 3px 10px; border-radius: 6px; font-size: 13px; font-weight: 600;'>{prop*100:.0f}%</span>
</div>
{f"<div style='font-size: 12px; color: #64748b;'>{html.escape(desc)}</div>" if desc else ""}
{f"<div style='font-size: 11px; color: #94a3b8; margin-top: 4px;'>{cluster_str}</div>" if cluster_str else ""}
</div>""")

        context_html = f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px; margin: 12px 0;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px;'>📊 맥락 분포</div>
{''.join(context_items)}
</div>"""
        st.markdown(context_html, unsafe_allow_html=True)

    # 시스템 의견 및 자가 평가 카드
    bottom_cards = []

    if notes:
        safe_notes = html.escape(notes).replace('\n', '<br>')
        bottom_cards.append(f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px;'>💬 Claude 분석 코멘트</div>
<div style='font-size: 13px; color: #334155; line-height: 1.6;'>{safe_notes}</div>
</div>""")

    diagnostics = claude_result.get("system_diagnostics", {})
    if diagnostics and any(diagnostics.values()):
        diag_items = []
        for key, label in [
            ("clustering_quality", "클러스터링 품질"),
            ("headword_presence_note", "표제어 출현율"),
            ("corpus_limitations", "코퍼스 한계"),
            ("embedding_limitations", "임베딩 한계"),
        ]:
            val = diagnostics.get(key)
            if val:
                safe_val = html.escape(str(val))
                diag_items.append(f"""<div style='margin-bottom: 8px;'>
<div style='font-size: 12px; font-weight: 600; color: #64748b;'>{label}</div>
<div style='font-size: 13px; color: #334155;'>{safe_val}</div>
</div>""")

        if diag_items:
            bottom_cards.append(f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px;'>⚙️ 시스템 자가 진단</div>
{''.join(diag_items)}
</div>""")

    if bottom_cards:
        if len(bottom_cards) == 2:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(bottom_cards[0], unsafe_allow_html=True)
            with col2:
                st.markdown(bottom_cards[1], unsafe_allow_html=True)
        else:
            st.markdown(bottom_cards[0], unsafe_allow_html=True)

    st.markdown("<hr style='margin: 24px 0; border: 0; border-top: 2px solid #e2e8f0;'>", unsafe_allow_html=True)

# ---------- 📋 기존 분석 결과 보기 (탭으로 lazy loading) ----------
st.markdown("### 📋 기존 분석 결과 보기")
st.caption("이미 완료된 클러스터링과 검증 결과를 확인하세요. 탭을 클릭하면 로드됩니다.")

result_tabs = st.tabs(["🔬 Claude 검증 결과", "🧬 클러스터 결과"])

# 탭1: Claude 검증 결과 (먼저 표시)
with result_tabs[0]:
    validations = fetch_validations(lemma)

    if not validations:
        st.info("이 단어에 대한 검증 이력이 없어요. 위의 '새로 검증하기'에서 분석을 시작하세요.")
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

        # 검증 결과 정렬: 신의미가 있는 검증을 먼저 표시
        def has_new_sense(validation):
            claude_result = validation[5]
            if isinstance(claude_result, str):
                claude_result = json.loads(claude_result)
            for sense in claude_result.get("senses", []):
                dict_matches = sense.get("dict_sense_matches", {})
                # 사전에 하나도 매칭 안 되면 신의미
                if dict_matches and not any(v is not None for v in dict_matches.values()):
                    return True
            return False

        # 정렬: 신의미 있으면 먼저(True=1, False=0), 같으면 최신순
        sorted_validations = sorted(validations, key=lambda v: (not has_new_sense(v), -v[6].timestamp() if hasattr(v[6], 'timestamp') else 0))

        st.caption(f"Claude로 검증한 총 {len(validations)}건의 이력 (신의미 우선, 최신 순)")
        for v in sorted_validations:
            render_validation_card(v, source_map)

# 탭2: 클러스터 결과
with result_tabs[1]:
    clusters = fetch_clusters_by_source(lemma, pos)

    if not clusters:
        st.info(
            f"'{lemma}' ({pos})에 대한 클러스터링 결과가 아직 없어요. "
            "위의 '새로 검증하기'에서 분석을 시작하세요."
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

                    # 클러스터 카드 헤더
                    header_html = f"""<div style='background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%); padding: 14px 18px; border-radius: 12px 12px 0 0; color: white;'>
<div style='font-size: 16px; font-weight: 600;'>
🧬 클러스터 {cluster_id} <span style='opacity: 0.9; font-size: 14px; margin-left: 8px;'>· {member_count:,}개 용례</span>
{f"<div style='font-size: 13px; opacity: 0.85; margin-top: 4px;'>🏷️ {html.escape(label)}</div>" if label else ""}
</div>
</div>"""
                    st.markdown(header_html, unsafe_allow_html=True)

                    # 대표 용례
                    examples = fetch_cluster_examples(cluster_id, lemma, limit=3)
                    if not examples:
                        st.caption("대표 용례 없음")
                    else:
                        examples_html = "<div style='background: #f8fafc; padding: 16px; border-radius: 0 0 12px 12px; margin-bottom: 20px;'>"
                        for idx, ex in enumerate(examples, 1):
                            similarity, text_id, comment_id, content, published_at, title, url = ex
                            if content:
                                safe_content = html.escape(content.replace("\n", " "))
                                safe_content = safe_content.replace(html.escape(lemma), f"<strong>{html.escape(lemma)}</strong>")

                                meta_parts = []
                                if published_at: meta_parts.append(str(published_at)[:10])
                                if similarity is not None: meta_parts.append(f"유사도 {similarity:.3f}")
                                meta_str = " · ".join(meta_parts)

                                examples_html += f"""<div style='background: white; padding: 12px; border-radius: 6px; border-left: 3px solid #8b5cf6; margin-bottom: 10px;'>
<div style='font-size: 14px; color: #334155; line-height: 1.6;'>{safe_content[:200]}{"..." if len(safe_content) > 200 else ""}</div>
{f"<div style='font-size: 12px; color: #64748b; margin-top: 6px;'>{meta_str}</div>" if meta_str else ""}
</div>"""
                        examples_html += "</div>"
                        st.markdown(examples_html, unsafe_allow_html=True)
