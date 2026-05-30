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

    st.title("🔒 어휘 사용 현황 및 발견 대시보드")
    password = st.text_input("비밀번호", type="password")
    if password == correct_password:
        st.session_state["password_correct"] = True
        st.rerun()
    elif password:
        st.error("비밀번호가 틀렸습니다")
        st.stop()
    else:
        st.stop()

AUTH_TOKEN = _make_token()
