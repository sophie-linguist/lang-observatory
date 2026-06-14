import streamlit as st

st.set_page_config(
    page_title="어휘 사용 현황 관찰 및 발견 대시보드",
    page_icon="📚",
    layout="wide",
)

#from auth import check_password
#check_password()

# CSS 스타일
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}

/* 마크다운 헤더 스타일 */
h1, h2 {
    color: #1E293B !important;
    font-weight: 700 !important;
    margin-top: 32px !important;
    margin-bottom: 16px !important;
}
h3, h4 {
    color: #334155 !important;
    font-weight: 600 !important;
    margin-top: 24px !important;
    margin-bottom: 12px !important;
}

/* 섹션 구분선 스타일 */
hr {
    border: 0 !important;
    border-top: 2px solid #E2E8F0 !important;
    margin: 32px 0 !important;
}

/* 리스트 스타일 */
ul, ol {
    line-height: 2 !important;
    padding-left: 24px !important;
}
li {
    margin: 8px 0 !important;
}
li strong {
    color: #667eea !important;
}

/* 코드 블록 스타일 */
code {
    background-color: #F1F5F9 !important;
    color: #667eea !important;
    padding: 3px 8px !important;
    border-radius: 5px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
}
pre {
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    padding: 16px !important;
    border-left: 4px solid #667eea !important;
}

/* 인용문 스타일 */
blockquote {
    border-left: 4px solid #667eea !important;
    background-color: #F8FAFC !important;
    padding: 16px 20px !important;
    border-radius: 0 10px 10px 0 !important;
    margin: 16px 0 !important;
}

/* 강조 텍스트 */
strong {
    color: #334155 !important;
    font-weight: 600 !important;
}

/* 본문 텍스트 */
p {
    line-height: 1.8 !important;
    color: #334155 !important;
    margin: 12px 0 !important;
}

/* 섹션 카드 스타일 */
.main .block-container {
    padding: 2rem !important;
}

/* 메인 콘텐츠 배경 */
[data-testid="stAppViewContainer"] {
    background-color: #FAFBFC !important;
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

# 메인 타이틀
st.markdown("""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 32px; border-radius: 16px; color: white; margin-bottom: 32px;'>
<div style='font-size: 36px; font-weight: 700; margin-bottom: 12px;'>📚 어휘 사용 현황 관찰 및 발견 대시보드</div>
<div style='font-size: 18px; opacity: 0.95;'>개인 연구용</div>
</div>""", unsafe_allow_html=True)

# 소개 카드
intro_html = """<div style='background: white; padding: 24px; border-radius: 12px; border: 1px solid #E2E8F0; margin: 24px 0;'>
<div style='font-size: 20px; font-weight: 600; color: #1E293B; margin-bottom: 16px;'>📖 시스템 소개</div>
<div style='background: #F8FAFC; padding: 16px; border-radius: 8px; border-left: 4px solid #667eea;'>
<p style='color: #334155; line-height: 1.8; margin: 0;'>
매일 한국어 텍스트를 자동으로 수집하여, <strong style='color: #667eea;'>사전에 없는 신어</strong>와 <strong style='color: #667eea;'>기존 단어의 새로운 의미</strong>를 발견하는 시스템입니다.
AI(Claude)가 의미 분석과 정의문 초안을 작성하고, 대시보드에서 확인·검증할 수 있습니다.
</p>
</div>
</div>"""
st.markdown(intro_html, unsafe_allow_html=True)

# 주요 기능 카드
features_html = """<div style='background: white; padding: 24px; border-radius: 12px; border: 1px solid #E2E8F0; margin: 24px 0;'>
<div style='font-size: 20px; font-weight: 600; color: #1E293B; margin-bottom: 20px;'>✨ 주요 기능</div>
<div style='display: grid; gap: 16px;'>
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 16px; border-radius: 10px; color: white;'>
        <div style='font-size: 16px; font-weight: 600; margin-bottom: 8px;'>💬 자연어 대화형 에이전트</div>
        <div style='font-size: 14px; opacity: 0.95;'>질문하면 AI가 적절한 도구를 호출하여 답변</div>
    </div>
    <div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border-left: 4px solid #10b981;'>
        <div style='font-size: 16px; font-weight: 600; color: #334155; margin-bottom: 8px;'>📊 실시간 동향 분석</div>
        <div style='font-size: 14px; color: #64748b;'>빈도 급등 단어, 신규 등장 어휘, 매체별 키워드 분석</div>
    </div>
    <div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border-left: 4px solid #f59e0b;'>
        <div style='font-size: 16px; font-weight: 600; color: #334155; margin-bottom: 8px;'>🔍 어휘 상세 탐색</div>
        <div style='font-size: 14px; color: #64748b;'>사용 빈도, 사전 정보, 시계열 추이, 실제 용례 확인</div>
    </div>
    <div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border-left: 4px solid #8b5cf6;'>
        <div style='font-size: 16px; font-weight: 600; color: #334155; margin-bottom: 8px;'>🤖 AI 의미 분석</div>
        <div style='font-size: 14px; color: #64748b;'>UMAP+HDBSCAN 클러스터링 + Claude 검증으로 의미 자동 분류</div>
    </div>
</div>
</div>"""
st.markdown(features_html, unsafe_allow_html=True)

# 기술 스택 카드
tech_html = """<div style='background: white; padding: 24px; border-radius: 12px; border: 1px solid #E2E8F0; margin: 24px 0;'>
<div style='font-size: 20px; font-weight: 600; color: #1E293B; margin-bottom: 16px;'>🛠️ 기술 스택</div>
<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;'>
    <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; text-align: center;'>
        <div style='font-size: 14px; font-weight: 600; color: #667eea;'>데이터 수집</div>
        <div style='font-size: 13px; color: #64748b; margin-top: 4px;'>Naver News API<br>YouTube Data API</div>
    </div>
    <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; text-align: center;'>
        <div style='font-size: 14px; font-weight: 600; color: #667eea;'>형태소 분석</div>
        <div style='font-size: 13px; color: #64748b; margin-top: 4px;'>Kiwi</div>
    </div>
    <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; text-align: center;'>
        <div style='font-size: 14px; font-weight: 600; color: #667eea;'>임베딩</div>
        <div style='font-size: 13px; color: #64748b; margin-top: 4px;'>BGE-M3 (1024-dim)</div>
    </div>
    <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; text-align: center;'>
        <div style='font-size: 14px; font-weight: 600; color: #667eea;'>클러스터링</div>
        <div style='font-size: 13px; color: #64748b; margin-top: 4px;'>UMAP + HDBSCAN</div>
    </div>
    <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; text-align: center;'>
        <div style='font-size: 14px; font-weight: 600; color: #667eea;'>AI 분석</div>
        <div style='font-size: 13px; color: #64748b; margin-top: 4px;'>Claude API</div>
    </div>
    <div style='background: #F8FAFC; padding: 12px; border-radius: 8px; text-align: center;'>
        <div style='font-size: 14px; font-weight: 600; color: #667eea;'>데이터베이스</div>
        <div style='font-size: 13px; color: #64748b; margin-top: 4px;'>PostgreSQL + pgvector</div>
    </div>
</div>
</div>"""
st.markdown(tech_html, unsafe_allow_html=True)

# 상세 문서는 expander로
with st.expander("📚 시스템 상세 문서 보기", expanded=False):
    st.markdown("""<div style='background: #F8FAFC; padding: 20px; border-radius: 10px;'>
    """, unsafe_allow_html=True)
    with open("/home/ssohe/lang-observatory/dashboard/어휘사용관찰시스템_종합정리.md", "r") as f:
        st.markdown(f.read())
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<hr style='margin: 32px 0; border: 0; border-top: 2px solid #E2E8F0;'>", unsafe_allow_html=True)

st.markdown("""<div style='background: #F8FAFC; padding: 16px; border-radius: 10px; border-left: 4px solid #667eea;'>
<div style='color: #64748B; font-size: 14px; line-height: 1.8;'>
📅 <strong>개발 시작:</strong> 2026-03-30 <span style='margin: 0 8px; color: #CBD5E1;'>|</span> <strong>운영 시작:</strong> 2026-05-30
</div>
</div>""", unsafe_allow_html=True)
