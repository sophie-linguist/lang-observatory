import os
import hashlib
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except:
    pass

def _make_token():
    secret = os.getenv("DASHBOARD_PASSWORD", "")
    return hashlib.sha256(f"lang_obs_{secret}".encode()).hexdigest()[:16]

def check_password():
    if st.session_state.get("password_correct", False):
        return True

    auth_param = st.query_params.get("auth")
    if auth_param == _make_token():
        st.session_state["password_correct"] = True
        return True

    correct_password = os.getenv("DASHBOARD_PASSWORD", "")
    if not correct_password:
        st.error("잠시 기다려 주세요.")
        st.stop()

    # 비밀번호 입력 화면 디자인
    st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Pretendard', -apple-system, sans-serif !important;
    }

    /* 비밀번호 입력창 스타일 */
    input[type="password"] {
        border: 2px solid #10b981 !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        font-size: 15px !important;
        transition: all 0.2s ease !important;
    }
    input[type="password"]:focus {
        border-color: #059669 !important;
        box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""<div style='background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 32px; border-radius: 16px; color: white; margin-bottom: 32px; text-align: center;'>
    <div style='font-size: 48px; margin-bottom: 16px;'>🔒</div>
    <div style='font-size: 28px; font-weight: 700; margin-bottom: 12px;'>보호된 페이지</div>
    <div style='font-size: 16px; opacity: 0.95;'>이 페이지는 비밀번호로 보호됩니다</div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""<div style='background: white; padding: 32px; border-radius: 12px; border: 1px solid #E2E8F0; max-width: 400px; margin: 0 auto;'>
    <div style='font-size: 18px; font-weight: 600; color: #1E293B; margin-bottom: 16px; text-align: center;'>비밀번호를 입력하세요</div>
    </div>""", unsafe_allow_html=True)

    password = st.text_input("비밀번호", type="password", label_visibility="collapsed", placeholder="비밀번호 입력")

    if password == correct_password:
        st.session_state["password_correct"] = True
        st.rerun()
    elif password:
        st.markdown("""<div style='background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 6px; margin: 16px 0;'>
        <span style='color: #991b1b; font-weight: 600;'>❌ 비밀번호가 틀렸습니다</span>
        </div>""", unsafe_allow_html=True)
        st.stop()
    else:
        st.markdown("""<div style='background: #f0fdf4; border-left: 4px solid #10b981; padding: 12px 16px; border-radius: 6px; margin: 16px 0;'>
        <span style='color: #065f46; font-weight: 500;'>💡 비밀번호를 입력하면 페이지에 접근할 수 있습니다</span>
        </div>""", unsafe_allow_html=True)
        st.stop()

def check_password_inline(purpose="이 기능"):
    """
    페이지 내부에서 특정 기능만 보호할 때 사용.
    인증되지 않았으면 비밀번호 입력 UI를 표시하고 False 반환.
    인증되었으면 True 반환.
    """
    if st.session_state.get("password_correct", False):
        return True

    correct_password = os.getenv("DASHBOARD_PASSWORD", "")
    if not correct_password:
        st.error("비밀번호가 설정되지 않았습니다.")
        return False

    # 인라인 비밀번호 입력 UI
    st.markdown(f"""<div style='background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 24px; border-radius: 12px; color: white; margin: 16px 0;'>
    <div style='font-size: 24px; margin-bottom: 8px;'>🔒 보호된 기능</div>
    <div style='font-size: 14px; opacity: 0.95;'>{purpose}은(는) 비밀번호로 보호됩니다</div>
    </div>""", unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        password = st.text_input(
            "비밀번호",
            type="password",
            key=f"inline_password_{purpose}",
            placeholder="비밀번호 입력"
        )
    with col2:
        check_btn = st.button("확인", key=f"check_{purpose}", type="primary", use_container_width=True)

    if check_btn:
        if password == correct_password:
            st.session_state["password_correct"] = True
            st.success("✅ 인증 완료!")
            st.rerun()
        else:
            st.error("❌ 비밀번호가 틀렸습니다")

    return False

AUTH_TOKEN = _make_token()
