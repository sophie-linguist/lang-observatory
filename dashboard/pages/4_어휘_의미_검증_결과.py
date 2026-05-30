"""
검증 결과 누적 페이지.
같은 단어의 여러 검증을 한 카드로 묶음.
"""
import streamlit as st
import sys
import json as _json
from collections import defaultdict
sys.path.insert(0, "/home/ssohe/lang-observatory/src")

from db import get_conn
from kwic import make_kwic

st.set_page_config(page_title="어휘 의미 검증 결과", layout="wide")

import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/dashboard")
from auth import check_password
check_password()

st.title("어휘 의미 검증 결과")

st.markdown("""
<style>
/* 1. 세련된 웹 폰트(Pretendard) 로드 및 앱 전체 적용 */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}

/* 타이틀 아이콘과 텍스트를 정렬하는 스타일 */

/* 아이콘 스타일 정의 */

/* 타이틀 텍스트 스타일 정의 */

/* 2. 마크다운 표 스타일 정돈 */
table {
    width: auto !important;
    min-width: 60%;
    max-width: 800px;
    border-collapse: collapse;
}
table td, table th {
    padding: 8px 16px !important;
    border-bottom: 1px solid #E2E8F0 !important;
}

/* 3. Expander를 세련된 '카드' 디자인으로 변경 */
[data-testid="stExpander"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04) !important;
    margin-bottom: 16px !important;
    transition: all 0.2s ease-in-out !important;
}

/* 4. 카드에 마우스 올렸을 때 강조 효과 */
[data-testid="stExpander"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 6px 16px -4px rgba(0, 0, 0, 0.08) !important;
}

/* 5. 카드 내부 타이틀 텍스트 색상 정돈 */
[data-testid="stExpander"] summary p {
    font-size: 16px !important;
    font-weight: 600 !important;
    color: #1E293B !important;
}

/* 팝오버 버튼 일괄 모던화 및 크기 정돈 */
div[data-testid="stPopover"] > button {
    width: 100% !important;
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    color: #475569 !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 8px 12px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    transition: all 0.2s ease !important;
}

div[data-testid="stPopover"] > button:hover {
    background-color: #F1F5F9 !important;
    border-color: #CBD5E1 !important;
    color: #0F172A !important;
}

/* 인용문 디자인 개선 */
blockquote {
    border-left: 4px solid #3B82F6 !important;
    background-color: #F8FAFC !important;
    padding: 12px 16px !important;
    border-radius: 0 8px 8px 0 !important;
    color: #334155 !important;
    margin: 8px 0 !important;
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=600)
def fetch_cluster_examples(cluster_ids_tuple):
    """클러스터 IDs의 멤버 용례를 가져옴."""
    if not cluster_ids_tuple:
        return []
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            ucm.embedding_id,
            e.segment_text AS content,
            COALESCE(t.published_at, c.published_at) AS pub_at,
            COALESCE(s_t.name, s_c.name) AS source_name,
            e.text_id, e.comment_id
        FROM usage_cluster_members ucm
        JOIN embeddings e ON ucm.embedding_id = e.embedding_id
        LEFT JOIN texts t ON e.text_id = t.text_id
        LEFT JOIN comments c ON e.comment_id = c.comment_id
        LEFT JOIN texts ct ON c.text_id = ct.text_id
        LEFT JOIN sources s_t ON t.source_id = s_t.source_id
        LEFT JOIN sources s_c ON ct.source_id = s_c.source_id
        WHERE ucm.cluster_id = ANY(%s)
        ORDER BY pub_at DESC NULLS LAST
        LIMIT 20
    """, (list(cluster_ids_tuple),))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


@st.cache_data(ttl=600, show_spinner="유사 용례 검색 중...")
def fetch_similar_examples(embedding_id, top_n=15):
    """임베딩 ID 하나와 가까운 다른 용례."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH target AS (
            SELECT embedding FROM embeddings WHERE embedding_id = %s
        )
        SELECT
            e.embedding_id,
            1 - (e.embedding <=> (SELECT embedding FROM target)) AS similarity,
            e.segment_text AS content,
            COALESCE(t.published_at, c.published_at) AS pub_at,
            COALESCE(s_t.name, s_c.name) AS source_name
        FROM embeddings e
        LEFT JOIN texts t ON e.text_id = t.text_id
        LEFT JOIN comments c ON e.comment_id = c.comment_id
        LEFT JOIN texts ct ON c.text_id = ct.text_id
        LEFT JOIN sources s_t ON t.source_id = s_t.source_id
        LEFT JOIN sources s_c ON ct.source_id = s_c.source_id
        WHERE e.embedding_id != %s
        ORDER BY e.embedding <=> (SELECT embedding FROM target)
        LIMIT %s
    """, (embedding_id, embedding_id, top_n))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# 분류별 이모지
JUDGMENT_EMOJI = {
    "신조어": "✦",
    "외래어·외국어": "🌐",
    "의미 변화": "🌱",
    "합성": "⊕",
    "파생": "⤴",
    "줄임말": "✂",
    "노이즈": "🚨",
}



@st.cache_data(ttl=300, show_spinner="검증 결과 가져오는 중...")
def load_validations():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT validation_id, headword, pos, n_clusters, n_examples,
               claude_result, judgment, created_at
        FROM sense_validation
        ORDER BY headword, created_at
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


validations = load_validations()

if not validations:
    st.info("아직 검증 결과 없음.")
    st.stop()

# 단어별 그룹화
grouped = defaultdict(list)
for v in validations:
    grouped[(v[1], v[2])].append(v)

# 정렬 옵션 (단어별)
col1, col2 = st.columns([3, 2])
with col1:
    sort_order = st.radio(
        "정렬",
        ["단어순", "최신 검증순", "검증 횟수 많은 순"],
        horizontal=True,
    )

st.caption(f"총 {len(grouped)}개 단어 · {len(validations)}건 검증")
st.divider()


def latest_at(group):
    return max(v[7] for v in group)


if sort_order == "최신 검증순":
    keys_sorted = sorted(grouped.keys(), key=lambda k: latest_at(grouped[k]), reverse=True)
elif sort_order == "검증 횟수 많은 순":
    keys_sorted = sorted(grouped.keys(), key=lambda k: -len(grouped[k]))
else:
    keys_sorted = sorted(grouped.keys())

SEARCH_PAGE = "/단어_의미_탐색"


def render_validation_block(v):
    """검증 1건의 본문을 그림."""
    validation_id, headword, pos, n_clusters, n_examples, claude_result, judgment, created_at = v
    if isinstance(claude_result, str):
        claude_result = _json.loads(claude_result)

    senses = claude_result.get("senses", [])
    notes = claude_result.get("notes", "")
    context_dist = claude_result.get("context_distribution", [])
    diagnostics = claude_result.get("system_diagnostics", {})
    emoji = JUDGMENT_EMOJI.get(judgment, "")

    _cids = [c for s in senses for c in s.get("cluster_ids_merged", [])]
    _src = ""
    if _cids:
        _cn = get_conn()
        _cr = _cn.cursor()
        _cr.execute("SELECT DISTINCT s.name FROM usage_clusters uc JOIN sources s ON uc.source_id = s.source_id WHERE uc.cluster_id = ANY(%s)", (_cids,))
        _src = " · ".join(r[0] for r in _cr.fetchall())
        _cr.close()
        _cn.close()

    st.markdown(f"### {emoji} {judgment} <span style='font-size:14px; font-weight:normal; color:#64748B;'> · 의미 {len(senses)}개 · 클러스터 {n_clusters}개 · 용례 {n_examples or '?'}개 · 매체: {_src} · {created_at.strftime('%Y-%m-%d %H:%M')}</span>", unsafe_allow_html=True)

    for sense in senses:
        sense_no = sense.get("sense_no", "?")
        definition = sense.get("definition", "")
        sense_type = sense.get("type", "")
        rep_example = sense.get("representative_example", "")
        syntax_info = sense.get("syntax_info", {})
        cluster_ids = sense.get("cluster_ids_merged", [])
        dict_matches = sense.get("dict_sense_matches", {})

        st.markdown(f"**🔹 의미 {sense_no}** — <span style='color: #2563EB; font-weight: 600;'>{sense_type}</span>", unsafe_allow_html=True)
        st.markdown(f"> {definition}")

        if rep_example:
            st.markdown(f"✏️ *대표 용례*: **{rep_example}**")

        # 데이터베이스 조회를 미리 한 번만 수행하여 효율성 확보
        examples = fetch_cluster_examples(tuple(cluster_ids)) if cluster_ids else []

        # 액션 버튼 두 개 가로 배치
        btn_cols = st.columns(2)

        with btn_cols[0]:
            if syntax_info:
                with st.popover("🔗 결합 정보 보기", use_container_width=True):
                    arg = syntax_info.get("argument_structure")
                    if arg:
                        st.markdown(f"**논항 구조**: `{arg}`")
                    for key, label in [
                        ("collocates", "공기어"),
                        ("common_modifiers", "수식어"),
                        ("preceding_patterns", "선행 패턴"),
                        ("following_patterns", "후행 패턴"),
                    ]:
                        items = syntax_info.get(key, [])
                        if items:
                            p_str = ", ".join(items)
                            st.markdown(f"**{label}**: {p_str}")

        with btn_cols[1]:
            if examples:
                toggle_key = f"show_examples_{validation_id}_{sense_no}"
                if toggle_key not in st.session_state:
                    st.session_state[toggle_key] = False

                if st.button(
                    f"📂 의미 용례 {len(examples)}건 {'숨기기' if st.session_state[toggle_key] else '보기'}",
                    key=f"toggle_{validation_id}_{sense_no}",
                    use_container_width=True
                ):
                    st.session_state[toggle_key] = not st.session_state[toggle_key]
                    st.rerun()

        # 의미 용례 펼침 (컬럼 밖, 본문 폭)
        if cluster_ids and st.session_state.get(f"show_examples_{validation_id}_{sense_no}", False):
            similar_key = f"similar_search_{validation_id}_{sense_no}"
            selected_emb_id = st.session_state.get(similar_key)

            if selected_emb_id:
                selected = [ex for ex in examples if ex[0] == selected_emb_id]
                examples_to_show = selected if selected else examples[:1]
            else:
                examples_to_show = examples

            st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 4px; color: #475569;'>📋 의미 용례 목록 (기본 5개 노출 / 스크롤 가능)</p>", unsafe_allow_html=True)
            
            # [개선 1] 5개 노출용 height=320 고정 컨테이너 적용
            with st.container(border=True, height=320):
                for ex_idx, (emb_id, content, pub_at, src_name, text_id, comment_id) in enumerate(examples_to_show):
                    pub_str = pub_at.strftime("%y-%m-%d") if pub_at else "?"
                    snippet = (content or "").replace("\n", " ")
                    
                    col_text, col_btn = st.columns([8.5, 1.5])
                    with col_text:
                        st.markdown(
                            f"<div style='padding: 8px 10px; font-size: 13.5px; background-color: #F8FAFC; border-radius: 6px; margin-bottom: 6px; line-height: 1.5; border-left: 3px solid #CBD5E1;'>"
                            f"<span style='color: #64748B; font-weight: 600;'>[{src_name} · {pub_str}]</span> {snippet}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    with col_btn:
                        if not selected_emb_id:
                            if st.button("🔍 유사 검색", key=f"sim_{validation_id}_{sense_no}_{ex_idx}", help="유사 용례 검색", use_container_width=True):
                                st.session_state[similar_key] = emb_id
                                st.rerun()
                        else:
                            if st.button("↩ 목록으로", key=f"back_{validation_id}_{sense_no}_{ex_idx}", help="용례 목록으로", use_container_width=True):
                                del st.session_state[similar_key]
                                st.rerun()

        # 유사 용례 검색 결과 표시 (세션 상태로 트리거)
        similar_key = f"similar_search_{validation_id}_{sense_no}"
        if similar_key in st.session_state:
            target_emb_id = st.session_state[similar_key]
            similar = fetch_similar_examples(target_emb_id, top_n=15)

            st.markdown("<p style='font-size: 14px; font-weight: 600; margin-bottom: 4px; color: #0D9488;'>🔗 유사 용례 결과 (기본 5개 노출 / 스크롤 가능)</p>", unsafe_allow_html=True)
            
            # [개선 2] 유사 용례 컨테이너 개별 height 지정 및 전체 스크롤 처리
            with st.container(border=True, height=320):
                title_col, close_col = st.columns([7, 3])
                with title_col:
                    st.caption(f"타겟 임베딩 ID: {target_emb_id} (검색된 유사 용례 {len(similar)}건)")
                with close_col:
                    if st.button("✕ 유사창 닫기", key=f"close_{similar_key}_top", use_container_width=True):
                        del st.session_state[similar_key]
                        st.rerun()

                # 기존의 [:5] 제약을 해제하여, 15건 모두 스크롤창 내부에서 순차 노출되도록 변경
                for sim_emb_id, similarity, content, pub_at, src_name in similar:
                    pub_str = pub_at.strftime("%y-%m-%d") if pub_at else "?"
                    snippet = (content or "").replace("\n", " ")
                    st.markdown(
                        f"<div style='padding: 8px 6px; font-size: 13.5px; border-bottom: 1px solid #F1F5F9; line-height: 1.4;'>"
                        f"<span style='color: #0D9488; font-weight: 700; margin-right: 8px;'>{similarity:.3f}</span> "
                        f"<span style='color: #64748B; font-weight: 500;'>[{src_name} · {pub_str}]</span> {snippet}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
        
        if dict_matches:
            non_null = {k: v for k, v in dict_matches.items() if v is not None}
            if non_null:
                st.caption(f"📚 사전 매칭: {non_null}")
            else:
                st.caption("📚 사전 매칭: 세 사전 모두 미등재")

        if cluster_ids:
            st.caption(f"🔢 통합된 클러스터 ID: {cluster_ids}")

        st.markdown("")

    if context_dist:
        st.markdown("**📊 맥락 분포**")
        ctx_cols = st.columns(len(context_dist))
        for idx, ctx in enumerate(context_dist):
            label = ctx.get("context_label", "")
            prop = ctx.get("proportion", 0)
            desc = ctx.get("description", "")
            with ctx_cols[idx]:
                st.metric(label=label, value=f"{prop*100:.0f}%", help=desc)

    # 카드 맨 아래 하단 버튼 배치 (의견 및 자가 평가 정돈)
    if notes or diagnostics:
        st.markdown("<hr style='margin: 16px 0; border: 0; border-top: 1px dashed #E2E8F0;'>", unsafe_allow_html=True)
        bottom_cols = st.columns([5, 1.2, 1.3])

        with bottom_cols[1]:
            if notes:
                with st.popover("📝 시스템 의견"):
                    st.markdown(notes)

        with bottom_cols[2]:
            if diagnostics:
                with st.popover("🔍 시스템 자가 평가"):
                    for key, label in [
                        ("clustering_quality", "클러스터링 품질"),
                        ("embedding_limitations", "임베딩 한계"),
                        ("corpus_limitations", "코퍼스 한계"),
                        ("headword_presence_note", "표제어 등장 여부"),
                    ]:
                        val = diagnostics.get(key)
                        if val:
                            st.markdown(f"**{label}**")
                            st.caption(val)


for (headword, pos) in keys_sorted:
    group = grouped[(headword, pos)]
    n_validations = len(group)

    # 그룹 헤더: 프리미엄 배지 형태 레이아웃
    latest = sorted(group, key=lambda v: v[7], reverse=True)[0]
    latest_judgment = latest[6]
    emoji = JUDGMENT_EMOJI.get(latest_judgment, "")

    count_str = f" ({n_validations}회 검증)" if n_validations > 1 else ""
    header = f" {headword}   |   {pos}   ·   {emoji} {latest_judgment}{count_str}"

    with st.expander(header, expanded=False):
        st.markdown(f"🔗 [단어 검색 페이지에서 상세히 보기]({SEARCH_PAGE}?word={headword})")
        st.markdown("")

        if n_validations == 1:
            render_validation_block(group[0])
        else:
            tab_labels = [
                f"📆 {v[7].strftime('%m/%d %H:%M')} ({v[6]})"
                for v in group
            ]
            tabs = st.tabs(tab_labels)
            for tab, v in zip(tabs, group):
                with tab:
                    render_validation_block(v)

st.divider()
