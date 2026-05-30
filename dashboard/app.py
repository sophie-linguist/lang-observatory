import streamlit as st

st.set_page_config(
    page_title="어휘 사용 관찰 및 발견 대시보드",
    page_icon="📚",
    layout="wide",
)

#from auth import check_password
#check_password()

# 깔끔하게 제목과 기본 안내만 남김
st.title("📚 어휘 사용 현황 및 발견 대시보드")
st.markdown("**내가 쓰려고 만든 도구**")

st.markdown("---")
with open("/home/ssohe/lang-observatory/dashboard/어휘사용관찰시스템_종합정리.md", "r") as f:
    st.markdown(f.read())

st.markdown("---")
st.caption("시작일: 2026-03-30 · 본인이 매일 쓰는 도구 형태로 만드는 것이 원칙")
