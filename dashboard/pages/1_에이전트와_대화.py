import streamlit as st
import sys
import json

sys.path.insert(0, "/home/ssohe/lang-observatory/src")
from analyzers.agent_loop import run_agent

st.set_page_config(page_title="에이전트와 대화", layout="wide")

import sys
sys.path.insert(0, "/home/ssohe/lang-observatory/dashboard")
from auth import check_password
check_password()

st.title("에이전트와 대화")

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
    background-color: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    margin: 4px 0 !important;
}
[data-testid="stExpander"] summary p {
    font-size: 13px !important;
    color: #64748B !important;
    font-family: 'JetBrains Mono', monospace !important;
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
    st.markdown("### 🤖 에이전트")
    st.caption(
        "본 시스템의 DB를 도구로 호출해 사용자 질문에 답합니다. "
        "어떤 도구를 호출했는지 답변 위에서 펼쳐 볼 수 있어요."
    )
    if st.button("🗑 대화 새로 시작", use_container_width=True):
        st.session_state.messages = []
        st.session_state.traces = []
        st.rerun()

    st.markdown("---")
    st.markdown("### 💡 예시 질문")
    examples = [
        "긁다 요즘 어떻게 쓰여?",
        "쌈디는 어떤 단어야?",
        "이번 주에 떠오른 단어 알려줘",
        "본 시스템이 지금까지 뭘 발견했어?",
        "국민배당금 매체별로 어떻게 달라?",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}", use_container_width=True):
            st.session_state.pending_query = ex
            st.rerun()


# ---------- 메시지 표시 ----------
def render_trace(trace: list):
    """도구 호출 트레이스를 펼침으로 표시."""
    if not trace:
        return
    summary = " · ".join(f"🔧 {step['tool_name']}" for step in trace if step['type'] == 'tool_use')
    with st.expander(f"도구 호출 내역 ({summary})", expanded=False):
        for step in trace:
            if step["type"] == "tool_use":
                st.markdown(f"**🔧 `{step['tool_name']}`** 호출")
                st.code(json.dumps(step["tool_input"], ensure_ascii=False, indent=2), language="json")
            elif step["type"] == "tool_result":
                st.markdown(f"**✓ `{step['tool_name']}`** 결과 (요약)")
                result = step["result"]
                # 너무 긴 결과는 잘라서 표시
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
