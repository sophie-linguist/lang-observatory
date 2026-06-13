import streamlit as st
import sys
import json

sys.path.insert(0, "/home/ssohe/lang-observatory/src")
from analyzers.agent_loop import run_agent

st.set_page_config(page_title="에이전트와 대화", layout="wide")

sys.path.insert(0, "/home/ssohe/lang-observatory/dashboard")
from auth import check_password
check_password()

st.markdown("""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 16px; color: white; margin-bottom: 24px;'>
<div style='font-size: 28px; font-weight: 700; margin-bottom: 8px;'>💬 에이전트와 대화</div>
<div style='font-size: 16px; opacity: 0.95;'>자연어로 질문하면 AI가 적절한 도구를 호출하여 답변합니다</div>
</div>""", unsafe_allow_html=True)

st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, [data-testid="stAppViewContainer"], .main .block-container {
    font-family: 'Pretendard', -apple-system, sans-serif !important;
}


/* 마크다운 표 폭 제한 */
table { width: auto !important; min-width: 60%; max-width: 800px; }
table td, table th { padding: 4px 12px !important; }

/* 도구 호출 펼침 카드 디자인 */
[data-testid="stExpander"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
    margin: 8px 0 !important;
    transition: all 0.2s ease-in-out !important;
}
[data-testid="stExpander"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.08) !important;
}
[data-testid="stExpander"] summary p {
    font-size: 14px !important;
    color: #475569 !important;
    font-weight: 500 !important;
    font-family: 'Pretendard', -apple-system, sans-serif !important;
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

/* 사이드바 버튼 디자인 */
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

/* 채팅 입력창 디자인 */
[data-testid="stChatInput"] {
    border: 2px solid #E2E8F0 !important;
    border-radius: 12px !important;
    padding: 4px !important;
    background-color: white !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
}

/* 채팅 메시지 디자인 */
[data-testid="stChatMessage"] {
    background-color: #F8FAFC !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin: 8px 0 !important;
    border: 1px solid #E2E8F0 !important;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
}
</style>
""", unsafe_allow_html=True)



# ---------- 세션 상태 ----------
if "messages" not in st.session_state:
    st.session_state.messages = []
# 각 assistant 메시지에 도구 호출 트레이스 같이 저장
if "traces" not in st.session_state:
    st.session_state.traces = []


# ---------- 사이드바 ----------
with st.sidebar:
    st.markdown("""<div style='text-align: center; padding: 20px 10px; margin-bottom: 20px;'>
    <div style='font-size: 24px; margin-bottom: 8px;'>🤖</div>
    <div style='font-size: 18px; font-weight: 600;'>AI 에이전트</div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""<div style='background: rgba(255, 255, 255, 0.15); padding: 12px; border-radius: 8px; margin-bottom: 16px;'>
    <div style='font-size: 13px; line-height: 1.6;'>
    DB를 도구로 호출하여 질문에 답합니다.<br>
    도구 호출 내역은 답변 위에서 확인할 수 있습니다.
    </div>
    </div>""", unsafe_allow_html=True)

    if st.button("🗑 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.traces = []
        st.rerun()

    st.markdown("<hr style='border-color: rgba(255, 255, 255, 0.3); margin: 24px 0;'>", unsafe_allow_html=True)

    st.markdown("""<div style='font-size: 16px; font-weight: 600; margin-bottom: 12px;'>💡 예시 질문</div>""", unsafe_allow_html=True)

    examples = [
        "최근 일주일 동안 급증한 단어는?",
        "네이버 뉴스와 유튜브에서 다르게 쓰이는 단어 찾아줘",
        "사전에 없는 신조어 중 빈도가 높은 것은?",
    ]
    for ex in examples:
        if st.button(f"💬 {ex}", key=f"ex_{ex}", use_container_width=True):
            st.session_state.pending_query = ex
            st.rerun()


# ---------- 메시지 표시 ----------
def render_trace(trace: list):
    """도구 호출 트레이스를 카드 스타일로 표시."""
    if not trace:
        return

    tool_names = [step['tool_name'] for step in trace if step['type'] == 'tool_use']
    summary = " · ".join(f"🔧 {name}" for name in tool_names)

    with st.expander(f"🛠️ 도구 호출 내역 ({len(tool_names)}개) — {summary}", expanded=False):
        for step in trace:
            if step["type"] == "tool_use":
                tool_html = f"""<div style='background: #f8fafc; border-left: 4px solid #8b5cf6; padding: 12px; border-radius: 6px; margin-bottom: 10px;'>
<div style='font-size: 14px; font-weight: 600; color: #334155; margin-bottom: 8px;'>
🔧 <code style='background: #e0e7ff; color: #4338ca; padding: 2px 8px; border-radius: 4px;'>{step['tool_name']}</code> 호출
</div>
</div>"""
                st.markdown(tool_html, unsafe_allow_html=True)
                st.code(json.dumps(step["tool_input"], ensure_ascii=False, indent=2), language="json")

            elif step["type"] == "tool_result":
                result_html = f"""<div style='background: #f0fdf4; border-left: 4px solid #10b981; padding: 12px; border-radius: 6px; margin: 10px 0;'>
<div style='font-size: 14px; font-weight: 600; color: #334155; margin-bottom: 8px;'>
✓ <code style='background: #d1fae5; color: #065f46; padding: 2px 8px; border-radius: 4px;'>{step['tool_name']}</code> 결과
</div>
</div>"""
                st.markdown(result_html, unsafe_allow_html=True)
                result = step["result"]
                result_str = json.dumps(result, ensure_ascii=False, indent=2, default=str)
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "\n... (생략)"
                st.code(result_str, language="json")


for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            # 트레이스가 있으면 답변 위에 펼침으로
            if i < len(st.session_state.traces):
                render_trace(st.session_state.traces[i])
        st.markdown(msg["content"])


# ---------- 입력 ----------
user_input = st.chat_input("질문을 입력하세요...")

# 예시 버튼 눌렀을 때
if "pending_query" in st.session_state:
    user_input = st.session_state.pending_query
    del st.session_state.pending_query

if user_input:
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.traces.append([])  # user에는 trace 없음

    with st.chat_message("user"):
        st.markdown(user_input)

    # 에이전트 실행
    with st.chat_message("assistant"):
        trace_placeholder = st.empty()
        content_placeholder = st.empty()
        trace = []
        final_text = ""

        # history는 직전까지의 user/assistant 텍스트 메시지만
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
        ]

        with st.spinner("생각 중..."):
            for event in run_agent(user_input, history=history):
                if event["type"] == "tool_use":
                    trace.append({
                        "type": "tool_use",
                        "tool_name": event["tool_name"],
                        "tool_input": event["tool_input"],
                    })
                    # 진행 상태 표시
                    with trace_placeholder.container():
                        st.caption(f"🔧 `{event['tool_name']}` 호출 중...")
                elif event["type"] == "tool_result":
                    trace.append({
                        "type": "tool_result",
                        "tool_name": event["tool_name"],
                        "result": event["result"],
                    })
                    with trace_placeholder.container():
                        st.caption(f"✓ `{event['tool_name']}` 결과 받음")
                elif event["type"] == "text":
                    final_text = event["content"]
                elif event["type"] == "error":
                    final_text = f"⚠️ {event['message']}"

        # 트레이스 펼침 렌더 (최종)
        trace_placeholder.empty()
        with trace_placeholder.container():
            render_trace(trace)
        content_placeholder.markdown(final_text)

    # 세션 상태 저장
    st.session_state.messages.append({"role": "assistant", "content": final_text})
    st.session_state.traces.append(trace)
