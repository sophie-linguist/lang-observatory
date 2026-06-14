"""
검증 결과 누적 페이지.
같은 단어의 여러 검증을 한 카드로 묶음.
"""
import streamlit as st
import sys
import json as _json
from collections import defaultdict
import html as html_module
sys.path.insert(0, "/home/ssohe/lang-observatory/src")

from db import get_conn
from kwic import make_kwic

st.set_page_config(page_title="AI 분석 결과 모아보기", layout="wide")

st.markdown("""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 16px; color: white; margin-bottom: 24px;'>
<div style='font-size: 28px; font-weight: 700; margin-bottom: 8px;'>🗂️ AI 분석 결과 모아보기</div>
<div style='font-size: 16px; opacity: 0.95;'>Claude로 검증한 모든 단어의 의미 분석 결과를 모아서 확인</div>
</div>""", unsafe_allow_html=True)

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

/* 인용문 디자인 개선 */
blockquote {
    border-left: 4px solid #3B82F6 !important;
    background-color: #F8FAFC !important;
    padding: 12px 16px !important;
    border-radius: 0 8px 8px 0 !important;
    color: #334155 !important;
    margin: 8px 0 !important;
}

/* Radio 버튼 → 버튼 그룹 스타일 */
[data-testid="stRadio"] {
    background: transparent !important;
    padding: 0 !important;
}
[data-testid="stRadio"] > div {
    display: flex !important;
    gap: 8px !important;
    flex-wrap: wrap !important;
}
[data-testid="stRadio"] label {
    background: white !important;
    border: 2px solid #E2E8F0 !important;
    border-radius: 10px !important;
    padding: 12px 20px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    flex: 1 !important;
    min-width: 140px !important;
    text-align: center !important;
}
[data-testid="stRadio"] label:hover {
    border-color: #667eea !important;
    background: #F8FAFC !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15) !important;
}
[data-testid="stRadio"] label[data-checked="true"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border-color: #667eea !important;
    color: white !important;
    font-weight: 600 !important;
}
[data-testid="stRadio"] label[data-checked="true"] span {
    color: white !important;
}
[data-testid="stRadio"] input[type="radio"] {
    display: none !important;
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

# 모든 클러스터 ID → 소스 이름 매핑을 한 번에 조회 (성능 개선)
@st.cache_data(ttl=300)
def build_cluster_source_map(validations_tuple):
    """모든 검증 결과의 클러스터 ID를 한 번에 조회해서 매핑 생성"""
    all_cluster_ids = set()
    for v in validations_tuple:
        claude_result = v[5]
        if isinstance(claude_result, str):
            claude_result = _json.loads(claude_result)
        for s in claude_result.get("senses", []):
            all_cluster_ids.update(s.get("cluster_ids_merged", []))

    if not all_cluster_ids:
        return {}

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT uc.cluster_id, s.name
        FROM usage_clusters uc
        JOIN sources s ON uc.source_id = s.source_id
        WHERE uc.cluster_id = ANY(%s)
    """, (list(all_cluster_ids),))
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return result

cluster_source_map = build_cluster_source_map(tuple(validations))

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

def has_new_sense_in_group(group):
    """그룹 내 검증 중 하나라도 신의미가 있는지 확인"""
    for validation in group:
        claude_result = validation[5]
        if isinstance(claude_result, str):
            claude_result = _json.loads(claude_result)
        for sense in claude_result.get("senses", []):
            dict_matches = sense.get("dict_sense_matches", {})
            if dict_matches and not any(v is not None for v in dict_matches.values()):
                return True
    return False

if sort_order == "최신 검증순":
    # 신의미가 있는 단어 먼저, 그 다음 최신순
    keys_sorted = sorted(grouped.keys(), key=lambda k: (not has_new_sense_in_group(grouped[k]), -latest_at(grouped[k]).timestamp()))
elif sort_order == "검증 횟수 많은 순":
    # 신의미가 있는 단어 먼저, 그 다음 검증 횟수 순
    keys_sorted = sorted(grouped.keys(), key=lambda k: (not has_new_sense_in_group(grouped[k]), -len(grouped[k])))
else:
    # 신의미가 있는 단어 먼저, 그 다음 가나다순
    keys_sorted = sorted(grouped.keys(), key=lambda k: (not has_new_sense_in_group(grouped[k]), k))

SEARCH_PAGE = "/단어_의미_탐색"


def render_validation_block(v, cluster_source_map):
    """검증 1건을 설계 원칙이 드러나게 표시."""
    validation_id, headword, pos, n_clusters, n_examples, claude_result, judgment, created_at = v
    if isinstance(claude_result, str):
        claude_result = _json.loads(claude_result)

    senses = claude_result.get("senses", [])
    notes = claude_result.get("notes", "")
    context_dist = claude_result.get("context_distribution", [])
    diagnostics = claude_result.get("system_diagnostics", {})

    # 클러스터 ID로 매체 이름 조회
    _cids = [c for s in senses for c in s.get("cluster_ids_merged", [])]
    _src = " · ".join(sorted(set(cluster_source_map.get(cid, "?") for cid in _cids))) if _cids else "(매체 정보 없음)"

    # 헤더: 설계 원칙 강조
    header_html = f"""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 16px; border-radius: 12px 12px 0 0; color: white; margin-top: 12px;'>
<div style='font-size: 18px; font-weight: 600; margin-bottom: 8px;'>
{judgment}
</div>
<div style='font-size: 14px; opacity: 0.9;'>
📊 {_src} | ⏰ {created_at.strftime('%Y-%m-%d %H:%M')}
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

    # 의미별 카드 (설계 원칙 강조)
    for sense in sorted_senses:
        sense_no = sense.get("sense_no", "?")
        definition = sense.get("definition", "")
        sense_type = sense.get("type", "")
        rep_example = sense.get("representative_example", "")
        syntax_info = sense.get("syntax_info", {})
        cluster_ids = sense.get("cluster_ids_merged", [])
        dict_matches = sense.get("dict_sense_matches", {})
        perspectives = sense.get("perspectives_used", [])

        # 사전 매칭 상태
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
        cluster_badge = f"<span style='background: #8b5cf6; color: white; padding: 4px 10px; border-radius: 6px; font-size: 12px;'>🧬 클러스터 {', '.join(map(str, cluster_ids))} 통합</span>" if cluster_ids else ""

        # 관점 배지
        perspective_badges = ""
        if perspectives:
            perspective_badges = " ".join([f"<span style='background: #6366f1; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;'>{html_module.escape(p)}</span>" for p in perspectives])

        # HTML escape for safe rendering
        safe_definition = html_module.escape(definition) if definition else ""
        safe_rep_example = html_module.escape(rep_example) if rep_example else ""

        sense_html = f"""<div style='background: #f8fafc; border-left: 4px solid #667eea; padding: 20px; border-radius: 8px; margin: 16px 0;'>
<div style='margin-bottom: 12px;'>
<span style='font-size: 20px; font-weight: 700; color: #1e293b;'>의미 {sense_no}</span>
<span style='margin-left: 12px;'>{new_badge}</span>
<div style='margin-top: 8px;'>{cluster_badge}</div>
</div>
<div style='font-size: 18px; font-weight: 600; color: #334155; margin: 16px 0; line-height: 1.6;'>
{safe_definition}
</div>
{f"<div style='background: white; padding: 14px; border-radius: 6px; border-left: 3px solid #3b82f6; margin: 12px 0; font-style: italic; color: #475569;'>{safe_rep_example}</div>" if safe_rep_example else ""}
<div style='margin-top: 12px;'>
<div style='font-size: 13px; color: #64748b; margin-bottom: 6px;'>📚 사전 매칭:</div>
<div>{' '.join(dict_badges) if dict_badges else '<span style="color: #94a3b8;">매칭 정보 없음</span>'}</div>
</div>
{f"<div style='margin-top: 10px;'><span style='font-size: 12px; color: #64748b;'>🏷️ 적용 관점:</span> {perspective_badges}</div>" if perspectives else ""}
</div>"""

        st.markdown(sense_html, unsafe_allow_html=True)

        # 결합 정보 카드
        if syntax_info:
            syntax_items = []
            arg = syntax_info.get("argument_structure")
            if arg:
                syntax_items.append(f"<div><span style='color: #64748b; font-weight: 600;'>논항 구조:</span> <code style='background: #f1f5f9; padding: 2px 6px; border-radius: 4px;'>{html_module.escape(arg)}</code></div>")

            for key, label, icon in [
                ("collocates", "공기어", "🔗"),
                ("common_modifiers", "수식어", "✏️"),
                ("preceding_patterns", "선행 패턴", "◀"),
                ("following_patterns", "후행 패턴", "▶"),
            ]:
                items = syntax_info.get(key, [])
                if items:
                    items_html = ", ".join([f"<span style='background: #e0e7ff; color: #4338ca; padding: 2px 6px; border-radius: 4px; font-size: 12px;'>{html_module.escape(it)}</span>" for it in items])
                    syntax_items.append(f"<div style='margin-top: 6px;'><span style='color: #64748b; font-weight: 600;'>{icon} {label}:</span> {items_html}</div>")

            if syntax_items:
                syntax_html = f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px; margin: 12px 0;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px;'>🔗 결합 정보</div>
{''.join(syntax_items)}
</div>"""
                st.markdown(syntax_html, unsafe_allow_html=True)

        # 의미 용례 토글 버튼
        if cluster_ids:
            toggle_key = f"show_examples_{validation_id}_{sense_no}"
            if toggle_key not in st.session_state:
                st.session_state[toggle_key] = False

            if st.button(
                f"📂 의미 용례 {'숨기기' if st.session_state[toggle_key] else '보기'}",
                key=f"toggle_{validation_id}_{sense_no}",
                use_container_width=True
            ):
                st.session_state[toggle_key] = not st.session_state[toggle_key]
                st.rerun()

        # 의미 용례 카드
        if cluster_ids and st.session_state.get(f"show_examples_{validation_id}_{sense_no}", False):
            examples = fetch_cluster_examples(tuple(cluster_ids))
            similar_key = f"similar_search_{validation_id}_{sense_no}"
            selected_emb_id = st.session_state.get(similar_key)

            if selected_emb_id:
                selected = [ex for ex in examples if ex[0] == selected_emb_id]
                examples_to_show = selected if selected else examples[:1]
            else:
                examples_to_show = examples

            examples_html = """<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px; margin: 12px 0;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px;'>📂 의미 용례 목록</div>
<div style='max-height: 320px; overflow-y: auto;'>"""

            for ex_idx, (emb_id, content, pub_at, src_name, text_id, comment_id) in enumerate(examples_to_show[:10]):
                pub_str = pub_at.strftime("%y-%m-%d") if pub_at else "?"
                safe_snippet = html_module.escape((content or "").replace("\n", " ")[:200])
                examples_html += f"""<div style='background: #f8fafc; padding: 10px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #8b5cf6;'>
<div style='font-size: 12px; color: #64748b; margin-bottom: 4px;'>
<span style='font-weight: 600;'>{html_module.escape(src_name or '?')}</span> · {pub_str}
</div>
<div style='font-size: 13px; color: #334155; line-height: 1.5;'>{safe_snippet}</div>
</div>"""

            examples_html += "</div></div>"
            st.markdown(examples_html, unsafe_allow_html=True)

    # 맥락 분포 카드
    if context_dist:
        context_items = []
        for ctx in context_dist:
            label = ctx.get("context_label", "")
            prop = ctx.get("proportion", 0)
            desc = ctx.get("description", "")
            cluster_ids_ctx = ctx.get("cluster_ids", [])
            cluster_str = f" · 클러스터 {', '.join(map(str, cluster_ids_ctx))}" if cluster_ids_ctx else ""

            context_items.append(f"""<div style='background: #f8fafc; padding: 12px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #6366f1;'>
<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;'>
<span style='font-size: 14px; font-weight: 600; color: #334155;'>{html_module.escape(label)}</span>
<span style='background: #6366f1; color: white; padding: 3px 10px; border-radius: 6px; font-size: 13px; font-weight: 600;'>{prop*100:.0f}%</span>
</div>
{f"<div style='font-size: 12px; color: #64748b;'>{html_module.escape(desc)}</div>" if desc else ""}
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
        safe_notes = html_module.escape(notes).replace('\n', '<br>')
        bottom_cards.append(f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px;'>📝 시스템 의견</div>
<div style='font-size: 13px; color: #334155; line-height: 1.6;'>{safe_notes}</div>
</div>""")

    if diagnostics and any(diagnostics.values()):
        diag_items = []
        for key, label in [
            ("clustering_quality", "클러스터링 품질"),
            ("embedding_limitations", "임베딩 한계"),
            ("corpus_limitations", "코퍼스 한계"),
            ("headword_presence_note", "표제어 등장 여부"),
        ]:
            val = diagnostics.get(key)
            if val:
                safe_val = html_module.escape(str(val))
                diag_items.append(f"""<div style='margin-bottom: 8px;'>
<div style='font-size: 12px; font-weight: 600; color: #64748b;'>{label}</div>
<div style='font-size: 13px; color: #334155;'>{safe_val}</div>
</div>""")

        if diag_items:
            bottom_cards.append(f"""<div style='background: white; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px;'>
<div style='font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 10px;'>🔍 시스템 자가 평가</div>
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
            render_validation_block(group[0], cluster_source_map)
        else:
            tab_labels = [
                f"📆 {v[7].strftime('%m/%d %H:%M')} ({v[6]})"
                for v in group
            ]
            tabs = st.tabs(tab_labels)
            for tab, v in zip(tabs, group):
                with tab:
                    render_validation_block(v, cluster_source_map)

st.divider()
