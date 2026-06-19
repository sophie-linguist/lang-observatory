import sys
import json
import html
import sqlite3
import unicodedata
from pathlib import Path
from functools import lru_cache

import streamlit as st

KOREAN_SPACING_DIR = Path(__file__).resolve().parent.parent.parent / "korean-spacing"
DICT_DB_PATH = KOREAN_SPACING_DIR / "dict.db"
RULES_PATH = KOREAN_SPACING_DIR / "띄어쓰기_조항_정리.json"
sys.path.insert(0, str(KOREAN_SPACING_DIR))

st.set_page_config(page_title="사전과 규정에 기반한 띄어쓰기 도구", layout="wide")

# ── 스타일 ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}
.main .block-container {
    max-width: 1360px;
    padding-top: 2rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

/* 큰 입력창 — 실제 박스는 BaseWeb 래퍼가 그린다 */
[data-testid="stTextInputRootElement"] {
    min-height: 68px !important;
    border-radius: 16px !important;
    border: 2px solid #e6e9f0 !important;
    box-shadow: 0 4px 16px rgba(16,24,40,.08) !important;
    background: #fff !important;
    display: flex !important;
    align-items: center !important;
    transition: border-color .15s, box-shadow .15s !important;
}
[data-testid="stTextInputRootElement"]:focus-within {
    border-color: #e8954a !important;
    box-shadow: 0 0 0 4px #fdf0dc, 0 4px 16px rgba(16,24,40,.08) !important;
}
/* 안쪽 input은 투명, 자체 테두리 제거 */
[data-testid="stTextInput"] [data-baseweb="base-input"] {
    background: transparent !important;
}
[data-testid="stTextInput"] input {
    font-size: 20px !important;
    font-weight: 600 !important;
    padding: 0 20px !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    letter-spacing: -.01em !important;
    height: 64px !important;
}
/* 조회(엔터) 버튼 — 입력창과 높이 맞추고 주황 테마 */
[data-testid="stFormSubmitButton"] button {
    min-height: 68px !important;
    border-radius: 14px !important;
    border: none !important;
    background: linear-gradient(135deg,#f5b14a 0%,#e07a3f 100%) !important;
    color: #fff !important;
    font-size: 17px !important;
    font-weight: 800 !important;
    box-shadow: 0 4px 16px rgba(224,122,63,.25) !important;
    transition: filter .12s, transform .06s !important;
}
[data-testid="stFormSubmitButton"] button:hover {
    filter: brightness(1.05) !important;
    color: #fff !important;
}
[data-testid="stFormSubmitButton"] button:active {
    transform: translateY(1px) !important;
}

/* 우리말샘 탭(탭 패널 안)의 검색창은 작게 되돌린다 */
[data-baseweb="tab-panel"] [data-testid="stTextInputRootElement"] {
    min-height: 44px !important;
    border-radius: 10px !important;
    border-width: 1px !important;
    box-shadow: none !important;
}
[data-baseweb="tab-panel"] [data-testid="stTextInput"] input {
    font-size: 15px !important;
    height: 40px !important;
    padding: 0 14px !important;
}

/* 결과 카드 */
.sp-opt-card {
    background:#fff; border:1px solid #e6e9f0; border-radius:14px;
    padding:16px 20px; box-shadow:0 1px 4px rgba(16,24,40,.06);
    position:relative; overflow:hidden;
}
.sp-opt-card::before {
    content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
}
.sp-opt-card.space::before { background:#15803d; }
.sp-opt-card.join::before  { background:#c2410c; }
.sp-pill { display:inline-block; font-size:12px; font-weight:800;
    padding:3px 10px; border-radius:999px; }
.sp-pill.space { color:#15803d; background:#e9f7ee; }
.sp-pill.join  { color:#c2410c; background:#ffedd5; }
.sp-val { font-size:26px; font-weight:800; letter-spacing:-.01em; margin-top:8px; }

/* 조항 카드 */
.rule-card {
    background:#fff; border:1px solid #e6e9f0; border-radius:12px;
    padding:12px 16px; box-shadow:0 1px 4px rgba(16,24,40,.06); margin-bottom:8px;
}
.rule-clause { font-weight:800; color:#b45309; background:#fdf0dc;
    border-radius:8px; padding:3px 10px; font-size:13px; display:inline-block; }
.rule-policy-space { font-size:12px; font-weight:800; color:#15803d; }
.rule-policy-join  { font-size:12px; font-weight:800; color:#c2410c; }
.rule-policy-both  { font-size:12px; font-weight:800; color:#b45309; }
.rule-policy-confirm { font-size:12px; font-weight:800; color:#1d4ed8; }
.rule-gist { color:#374151; font-size:14px; margin:6px 0 0; line-height:1.5; font-weight:600; }
.rule-text { color:#1f2937; font-size:13.5px; margin:8px 0 0; line-height:1.55;
    padding:8px 11px; background:#f9fafb; border-radius:8px; border:1px solid #eef0f4; }
.rule-comment { color:#6b7280; font-size:12.5px; margin:6px 0 0; line-height:1.6; }

/* 사전 뜻풀이 */
.dict-entry { background:#fff; border:1px solid #e6e9f0; border-radius:12px;
    padding:11px 14px; box-shadow:0 1px 4px rgba(16,24,40,.06); margin-bottom:6px; }
.dict-word  { font-weight:800; font-size:15px; }
.dict-pos   { font-size:12px; color:#6b7280; background:#f3f4f6;
    border-radius:6px; padding:2px 8px; margin-left:6px; }
.dict-badge { font-size:11.5px; color:#475569; margin-left:6px; }
.dict-def   { color:#4b5563; font-size:13px; margin-top:4px; line-height:1.5; }

/* 분리 카드 */
.seg-card { background:#fff7ed; border:1px solid #fde6c8; border-radius:12px;
    padding:12px 16px; margin-bottom:8px; }
.seg-head { font-weight:800; color:#b45309; font-size:14px; }

/* 우리말샘 결과 */
.urim-entry { background:#fff; border:1px solid #e6e9f0; border-radius:10px;
    padding:10px 14px; margin-bottom:6px; }
.urim-word { font-weight:800; font-size:14px; }
.urim-pos  { font-size:11px; color:#6b7280; background:#f3f4f6;
    border-radius:5px; padding:2px 7px; margin-left:5px; }
.urim-def  { color:#4b5563; font-size:13px; margin-top:3px; line-height:1.5; }

/* 규정 익스팬더 스타일 조정 */
[data-testid="stExpander"] {
    border: 1px solid #e6e9f0 !important;
    border-radius: 10px !important;
    box-shadow: none !important;
    margin-bottom: 4px !important;
    background: #fff !important;
}
[data-testid="stExpander"]:hover {
    border-color: #f3d4a8 !important;
}

/* 구분선 */
.col-divider {
    border-left: 1px solid #e6e9f0;
    height: 100%;
    min-height: 600px;
    margin: 0 auto;
    width: 1px;
}

/* 탭 — 세그먼트(pill) 스타일 */
[data-baseweb="tab-list"] {
    background: #f3f4f6 !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    border-bottom: none !important;
}
[data-testid="stTab"] {
    border-radius: 9px !important;
    padding: 8px 16px !important;
    background: transparent !important;
    color: #6b7280 !important;
    font-weight: 700 !important;
    transition: background .12s, color .12s !important;
}
[data-testid="stTab"]:hover {
    color: #374151 !important;
    background: rgba(255,255,255,.5) !important;
}
[data-testid="stTab"][aria-selected="true"] {
    background: #fff !important;
    color: #1b1f27 !important;
    box-shadow: 0 1px 3px rgba(16,24,40,.12) !important;
}
/* 기본 밑줄 하이라이트 제거 */
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


# ── 헤더 배너 ─────────────────────────────────────────────────────
st.markdown("""
<div style='background:linear-gradient(135deg,#f5b14a 0%,#e07a3f 100%);
            padding:24px 28px; border-radius:16px; color:white; margin-bottom:28px;'>
  <div style='font-size:28px; font-weight:700; margin-bottom:6px;'>
    📏 한국어 띄어쓰기는 어려워
  </div>
  <div style='font-size:15px; opacity:.9;'>
    고쳐주지 않고, 한글 맞춤법과 사전으로 근거를 보여드립니다.
  </div>
</div>
""", unsafe_allow_html=True)


# ── 데이터 로딩 ───────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_rules() -> list[dict]:
    if not RULES_PATH.exists():
        return []
    with open(RULES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("조항", [])

@lru_cache(maxsize=1)
def _rule_map() -> dict:
    """항번호 → 조항 dict(조항 원문·예시·해설)."""
    return {r["항번호"]: r for r in _load_rules()}

def _search_urimalsaem(query: str, limit: int = 25) -> list[dict]:
    q = "".join(unicodedata.normalize("NFC", query.strip()).split())
    if not q:
        return []
    con = sqlite3.connect(str(DICT_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT word_raw, word_joined, pos, definition, type, target_code
        FROM entries
        WHERE word_joined LIKE ?
        ORDER BY length(word_joined), target_code
        LIMIT ?
    """, (f"%{q}%", limit)).fetchall()
    con.close()
    # 동일 word_joined 중복 제거 (뜻풀이만 다른 경우 대표 하나만)
    seen: set[str] = set()
    result = []
    for r in rows:
        key = (r["word_joined"], r["pos"] or "")
        if key not in seen:
            seen.add(key)
            result.append(dict(r))
    return result

RULE_SUMMARY = {
    "제2항":  "각 단어는 띄어 씀",
    "제41항": "조사는 앞말에 붙여 씀",
    "제42항": "의존 명사는 띄어 씀",
    "제43항": "단위 명사는 띄어 씀",
    "제44항": "수는 만 단위로 띄어 씀",
    "제45항": "열거하는 말은 띄어 씀",
    "제46항": "단음절 연속은 붙여 쓸 수 있음",
    "제47항": "보조 용언은 띄어 씀 (붙여 씀 허용)",
    "제48항": "성·이름은 붙여, 호칭은 띄어 씀",
    "제49항": "고유 명사는 단어별로 띄어 씀",
    "제50항": "전문 용어는 단어별로 띄어 씀",
}


# ── dict.db / core 확인 ───────────────────────────────────────────
if not DICT_DB_PATH.exists():
    st.error(f"**dict.db 파일이 없습니다.** `{DICT_DB_PATH}` 경로에 복사해 주세요.")
    st.stop()

try:
    from core import inspect as spacing_inspect  # type: ignore
except Exception as e:
    st.error(f"core 모듈 로드 실패: {e}")
    st.stop()


# ── 세션 상태 ─────────────────────────────────────────────────────
if "spacing_query" not in st.session_state:
    st.session_state.spacing_query = ""


# ── 메인 레이아웃 (좌 | 구분선 | 우) ─────────────────────────────
left, gap, right = st.columns([1, 0.04, 1])


# ════════════════════════════════════════════════════════════════
#  LEFT — 띄어쓰기 도구
# ════════════════════════════════════════════════════════════════
with left:
    with st.form("spacing_form", border=False, clear_on_submit=False):
        in_col, btn_col = st.columns([5, 1])
        with in_col:
            st.text_input(
                "표현 입력",
                max_chars=20,
                placeholder="",
                label_visibility="collapsed",
                key="spacing_input",
            )
        with btn_col:
            submitted = st.form_submit_button("조회", use_container_width=True)

    if submitted:
        st.session_state.spacing_query = st.session_state.spacing_input
    query = st.session_state.spacing_query

    if not query or not query.strip():
        pass
    else:
        try:
            result = spacing_inspect(query.strip(), db_path=str(DICT_DB_PATH))
        except Exception as e:
            st.error(f"분석 중 오류: {e}")
            result = None

        if result:
            st.divider()

            def empty_note(msg: str):
                st.markdown(
                    f"<div style='color:#9ca3af;font-size:13px;padding:4px 2px 8px;'>{html.escape(msg)}</div>",
                    unsafe_allow_html=True,
                )

            # ① 사전 정보 — 단어·품사만 보이고 뜻풀이는 오른쪽 '우리말샘 검색'으로 유도.
            #    (의미 단위 빈도가 없어 동음이의 중 정확한 뜻 선택이 불가하므로 뜻은 생략)
            st.markdown("#### 한 단어인가요?")
            if result.entries:
                seen_wp = set()
                for e in result.entries:
                    key = (e.word, e.pos)
                    if key in seen_wp:
                        continue
                    seen_wp.add(key)
                    badge = f"<span class='dict-badge'>{html.escape(e.spacing_badge)}</span>" if e.spacing_badge else ""
                    role = getattr(e, "role", None)
                    role_html = ""
                    if role:
                        if "정확도 높음" in role:
                            rc = "background:#e9f7ee;color:#15803d;"
                        elif "참고" in role:
                            rc = "background:#f3f4f6;color:#6b7280;"
                        else:
                            rc = "background:#fdf0dc;color:#b45309;"
                        role_html = (
                            f"<span style='{rc}font-size:11px;font-weight:800;"
                            f"padding:2px 9px;border-radius:999px;margin-right:6px;'>"
                            f"{html.escape(role)}</span>"
                        )
                    inner = (
                        f"<div style='display:flex;align-items:center;flex-wrap:wrap;gap:2px;'>"
                        f"{role_html}"
                        f"<span class='dict-word'>{html.escape(e.word)}</span>"
                        f"<span class='dict-pos'>{html.escape(e.pos)}</span>"
                        f"{badge}</div>"
                    )
                    st.markdown(f"<div class='dict-entry'>{inner}</div>", unsafe_allow_html=True)
            else:
                empty_note("우리말샘에 등재된 표제어를 찾지 못했습니다.")

            # ② 어떤 규정을 따르나요?
            st.markdown("#### 어떤 규정을 따르나요?")
            if result.rule_hints:
                for rh in result.rule_hints:
                    policy_raw = rh.원칙허용
                    if "확인" in policy_raw:
                        pcls, plabel = "rule-policy-confirm", "✓ 이미 맞음"
                    elif "+" in policy_raw or "허용" in policy_raw:
                        pcls, plabel = "rule-policy-both", "원칙 / 허용"
                    elif "원칙" in policy_raw:
                        pcls, plabel = "rule-policy-space", "원칙"
                    else:
                        pcls, plabel = "rule-policy-join", policy_raw
                    # 조항 원문 + 해설 요약을 함께 보여 준다.
                    clause = _rule_map().get(rh.항번호)
                    clause_html = ""
                    if clause:
                        clause_text = clause.get("조항", "") or ""
                        commentary = clause.get("해설") or clause.get("비고") or ""
                        if len(commentary) > 180:
                            commentary = commentary[:180].rstrip() + "…"
                        if clause_text:
                            clause_html += f"<div class='rule-text'>{html.escape(clause_text)}</div>"
                        if commentary:
                            clause_html += f"<div class='rule-comment'>{html.escape(commentary)}</div>"
                    st.markdown(f"""
<div class='rule-card'>
  <span class='rule-clause'>{html.escape(rh.항번호)}</span>
  <span class='{pcls}' style='margin-left:8px;'>{html.escape(plabel)}</span>
  <p class='rule-gist'>{html.escape(rh.요지)}</p>
  {clause_html}
</div>""", unsafe_allow_html=True)
            else:
                empty_note("적용되는 띄어쓰기 조항을 찾지 못했습니다.")

            # ③ 어떻게 띄어 쓰나요? (표기 방법 + 나눠쓰기)
            st.markdown("#### 어떻게 띄어 쓰나요?")
            if result.spacing_options:
                opt_cols = st.columns(min(len(result.spacing_options), 3))
                for i, opt in enumerate(result.spacing_options):
                    is_spaced = " " in opt
                    cls = "space" if is_spaced else "join"
                    label = "띄어 씀" if is_spaced else "붙여 씀"
                    with opt_cols[i % len(opt_cols)]:
                        st.markdown(f"""
<div class='sp-opt-card {cls}'>
  <span class='sp-pill {cls}'>{html.escape(label)}</span>
  <div class='sp-val'>{html.escape(opt)}</div>
</div>""", unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)
            else:
                empty_note("띄어쓰기 표기를 판정할 근거를 찾지 못했습니다.")
                if result.hint:
                    empty_note(result.hint)

            # 나눠쓰기 (판정 보조)
            if result.segmentation:
                seg = result.segmentation
                for cand in seg.candidates:
                    st.markdown(f"""
<div class='seg-card'>
  <div class='seg-head'>{html.escape(seg.message)}</div>
  <div style='font-size:15px;margin-top:4px;'>
    <b style='color:#9a3412;'>{html.escape(cand.original)}</b>
    &nbsp;→&nbsp; {html.escape(cand.left)} &nbsp;+&nbsp; {html.escape(cand.right)}
  </div>
  <div style='font-size:13px;color:#92400e;margin-top:4px;'>{html.escape(cand.hint)}</div>
</div>""", unsafe_allow_html=True)

            # ④ 어떤 순서로 찾았나요? — 탐색 경로(판정 후 표시)
            path = getattr(result, "inspection_path", None)
            if path:
                with st.expander("🔎 어떤 순서로 찾았는지 보기"):
                    steps = "".join(
                        f"<li style='margin:3px 0;'>{html.escape(s)}</li>" for s in path
                    )
                    st.markdown(
                        "<ol style='font-size:13px;color:#4b5563;line-height:1.6;"
                        f"padding-left:20px;margin:4px 0;'>{steps}</ol>",
                        unsafe_allow_html=True,
                    )


# ── gap 구분선 ────────────────────────────────────────────────────
with gap:
    st.markdown("<div class='col-divider'></div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
#  RIGHT — 참조 패널
# ════════════════════════════════════════════════════════════════
with right:
    tab_rules, tab_dict = st.tabs(["📋 한글 맞춤법 띄어쓰기 규정", "🔍 우리말샘 검색"])

    # ── 규정 탭 ─────────────────────────────────────────────────
    with tab_rules:
        st.markdown("""
<p style='color:#6b7280;font-size:13px;margin:4px 0 14px;'>
  한글맞춤법 제5장 띄어쓰기 (제41~50항) 및 기본 원칙 제2항
</p>""", unsafe_allow_html=True)

        rules = _load_rules()
        rule_map = {r["항번호"]: r for r in rules}

        for num, summary in RULE_SUMMARY.items():
            rule = rule_map.get(num)
            # 헤더에 요약 대신 조항 원문을 보여 준다(원문 없으면 요약으로 폴백).
            header_text = (rule.get("조항", "") if rule else "") or summary
            with st.expander(f"**{num}**　{header_text}"):
                if rule:
                    st.markdown(f"> {rule.get('조항', '')}")
                    exs = rule.get("예시") or []
                    if exs:
                        st.markdown("**예시**&nbsp;&nbsp;" + "&ensp;".join(f"`{e}`" for e in exs))
                    note = rule.get("해설") or rule.get("비고") or ""
                    if note:
                        st.markdown("---")
                        st.markdown(f"<div style='font-size:13px;color:#4b5563;line-height:1.7;'>{html.escape(note)}</div>",
                                    unsafe_allow_html=True)
                else:
                    st.caption("규정 데이터 없음")

    # ── 우리말샘 탭 ─────────────────────────────────────────────
    with tab_dict:
        st.markdown("""
<p style='color:#6b7280;font-size:13px;margin:4px 0 14px;'>
  우리말샘(opendict.korean.go.kr) 데이터 기반 로컬 검색
</p>""", unsafe_allow_html=True)

        dict_query = st.text_input(
            "사전 검색",
            placeholder="단어를 입력하세요",
            label_visibility="collapsed",
            key="dict_search_input",
        )

        if dict_query and dict_query.strip():
            with st.spinner("검색 중…"):
                entries = _search_urimalsaem(dict_query.strip())

            if entries:
                st.markdown(f"<p style='font-size:13px;color:#6b7280;margin-bottom:10px;'>"
                            f"검색 결과 {len(entries)}건</p>", unsafe_allow_html=True)
                for e in entries:
                    raw = e.get("word_raw") or e.get("word_joined") or ""
                    display_word = raw.replace("^", " ").strip()
                    pos = e.get("pos") or ""
                    definition = e.get("definition") or ""
                    tc = e.get("target_code")
                    link = ""
                    if tc:
                        link = (f"<a href='https://opendict.korean.go.kr/dictionary/view?sense_no={tc}' "
                                f"target='_blank' style='font-size:11px;color:#6b7280;margin-left:8px;"
                                f"text-decoration:none;'>우리말샘 ↗</a>")
                    st.markdown(f"""
<div class='urim-entry'>
  <div>
    <span class='urim-word'>{html.escape(display_word)}</span>
    <span class='urim-pos'>{html.escape(pos)}</span>
    {link}
  </div>
  <div class='urim-def'>{html.escape(definition)}</div>
</div>""", unsafe_allow_html=True)
            else:
                st.info(f"「{dict_query.strip()}」에 해당하는 항목이 없습니다.")
        else:
            st.markdown("""
<p style='color:#9ca3af;font-size:14px;margin-top:4px;'>
  단어를 입력하면 사전 뜻풀이가 여기에 나타납니다.
</p>""", unsafe_allow_html=True)
