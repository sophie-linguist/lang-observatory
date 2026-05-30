"""Claude tool-use 루프. 도구 호출 반복하며 사용자 질문에 답.

흐름:
  user → claude → tool_use → execute tool → tool_result → claude → text response
"""
import os
import sys
import json
from typing import Iterator
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analyzers"))

from analyzers.agent_tools import (
    lookup_word,
    freq_by_source,
    find_emerging_words,
    validate_sense,
    system_overview,
)


TOOLS = [
    {
        "name": "lookup_word",
        "description": (
            "특정 단어 하나에 대한 모든 정보(빈도, 사전 등재 의미, 신어 후보 상태, "
            "Claude로 검증한 의미 분석 결과)를 조회합니다. "
            "사용자가 단어의 뜻, 사용 양상, 사전 비교를 물을 때 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lemma": {"type": "string", "description": "조회할 단어"},
                "pos": {
                    "type": "string",
                    "description": "품사 (선택). NNG, NNP, VV, VA 등. NNG·NNP 단어는 'NNG·NNP'로 합쳐 입력. 생략 시 가장 흔한 품사 사용.",
                },
            },
            "required": ["lemma"],
        },
    },
    {
        "name": "freq_by_source",
        "description": (
            "특정 단어의 매체별·시기별 사용 빈도를 조회합니다. "
            "사용자가 단어가 언제 어디서 많이 쓰였는지, 매체별로 어떻게 다른지 물을 때 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lemma": {"type": "string"},
                "pos": {"type": "string"},
                "days": {
                    "type": "integer",
                    "description": "조회 기간 (일). 기본 90.",
                },
            },
            "required": ["lemma"],
        },
    },
    {
        "name": "find_emerging_words",
        "description": (
            "최근에 떠오른 단어 목록을 조회합니다. 사용자가 '요즘 어떤 단어가 많이 쓰여?', "
            "'최근 신어 후보 뭐가 있어?', '매체별로 어떤 키워드가 떴어?' 등을 물을 때 사용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "조회 기간 (일). 기본 7.",
                },
            },
        },
    },
    {
        "name": "validate_sense",
        "description": (
            "특정 단어의 의미를 클러스터링하고 Claude로 검증합니다. 2~6분 소요. "
            "사용자가 명시적으로 검증·분석을 요청하거나 lookup_word 결과 검증 이력이 없을 때 사용. "
            "함부로 호출하지 말고, 사용자에게 시간이 걸린다고 알리고 동의받은 후 호출."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lemma": {"type": "string"},
                "pos": {"type": "string"},
                "source_id": {
                    "type": "integer",
                    "description": "매체 ID. 3=네이버뉴스, 4=유튜브, 6=모두의말뭉치_신문, 5=모두의말뭉치_일상대화, 7=유튜브 댓글.",
                },
            },
            "required": ["lemma", "pos", "source_id"],
        },
    },
    {
        "name": "system_overview",
        "description": (
            "본 시스템이 지금까지 관측·검증한 결과의 종합 통계를 조회합니다. "
            "사용자가 '이 시스템이 뭘 발견했어?', '지금까지 검증한 단어 알려줘', "
            "'코퍼스 수집 현황 어때?' 등을 물을 때 사용."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


TOOL_FUNCTIONS = {
    "lookup_word": lookup_word,
    "freq_by_source": freq_by_source,
    "find_emerging_words": find_emerging_words,
    "validate_sense": validate_sense,
    "system_overview": system_overview,
}


SYSTEM_PROMPT = """당신은 한국어 어휘 관측 시스템의 분석 어시스턴트입니다.

본 시스템은 다음을 관측·수집합니다:
- 모두의말뭉치 신문 (2019~2023), 일상대화 (2020~2024)
- 네이버뉴스, 유튜브 영상·댓글 (2026년 3월~ 실시간 수집)
- 단어별 일자별 빈도, 임베딩 기반 의미 클러스터링, Claude로 의미 검증

당신은 위 도구를 사용해 사용자 질문에 답합니다. 답변 원칙:

1. **데이터에 기반해서 답하세요.** 일반 상식이 아니라 본 시스템의 DB에서 조회한 결과를 활용합니다.

2. **본 시스템의 한계를 솔직히 인정하세요.** system_diagnostics에 자가 진단(코퍼스 편중, 임베딩 토픽 잡음 등)이 들어 있으면 답변에 자연스럽게 반영합니다. 예: "코퍼스가 유튜브 댓글에 좀 치우쳐 있긴 한데..." 같은 식.

3. **친구랑 대화하듯 편한 톤 + 쉬운 표현으로.** 마크다운 헤딩(##, ###)은 쓰지 마세요. 학술·전문용어는 피하고, 전문 지식이 없는 친구에게 설명할 때 쓸 만한 말로 풀어 줍니다. 사람이 듣기 편한 한국어로 정리하고, 도구 결과를 JSON으로 뱉지 마세요. 꼭 목록이 필요할 때만 짧게.

4. **모르는 단어**: lookup_word 결과 데이터 없으면 "본 시스템 코퍼스에서는 아직 안 잡힌 단어"라고 안내. validate_sense는 시간이 오래 걸리므로 사용자가 명시적으로 요청한 경우만.

5. **간결함**: 사용자 질문에 직접 답하고, 추가 질문을 자연스럽게 권하되 길게 늘리지 않습니다. 보통 3~6문장 정도. 한 문단으로 답변하세요.
"""



def run_agent(user_message: str, history: list = None, model: str = "claude-opus-4-7") -> Iterator[dict]:
    """에이전트 루프. 사용자 메시지에 답하기까지 yield로 단계 진행 알림.

    yield 형식:
      {"type": "tool_use", "tool_name": "...", "tool_input": {...}}
      {"type": "tool_result", "tool_name": "...", "result": {...}}
      {"type": "text", "content": "..."}  # 최종 답변
      {"type": "error", "message": "..."}
    """
    client = Anthropic()

    if history is None:
        history = []

    messages = history + [{"role": "user", "content": user_message}]

    max_iters = 10  # 무한 루프 방지
    for _ in range(max_iters):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            yield {"type": "error", "message": f"API 호출 실패: {e}"}
            return

        # 응답 처리
        if response.stop_reason == "end_turn":
            # 최종 텍스트 답변
            for block in response.content:
                if block.type == "text":
                    yield {"type": "text", "content": block.text}
            return

        elif response.stop_reason == "tool_use":
            # 도구 호출 — assistant 메시지에 content 통째 추가
            messages.append({"role": "assistant", "content": response.content})

            # 각 tool_use 블록 처리
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    yield {
                        "type": "tool_use",
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                    }

                    # 도구 실행
                    fn = TOOL_FUNCTIONS.get(tool_name)
                    if fn is None:
                        result = {"error": f"알 수 없는 도구: {tool_name}"}
                    else:
                        try:
                            result = fn(**tool_input)
                        except Exception as e:
                            result = {"error": f"도구 실행 실패: {e}"}

                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "result": result,
                    }

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })

            # 도구 결과를 user 메시지로 추가
            messages.append({"role": "user", "content": tool_results})

        else:
            # 기타 stop_reason (max_tokens 등)
            yield {"type": "error", "message": f"예상치 못한 stop_reason: {response.stop_reason}"}
            return

    yield {"type": "error", "message": "최대 반복 횟수 초과"}


if __name__ == "__main__":
    # 테스트
    test_messages = [
        "긁다 요즘 어떻게 쓰여?",
    ]
    for msg in test_messages:
        print(f"\n{'='*60}\n사용자: {msg}\n{'='*60}")
        for event in run_agent(msg):
            if event["type"] == "tool_use":
                print(f"[🔧 {event['tool_name']}({event['tool_input']})]")
            elif event["type"] == "tool_result":
                print(f"[✓ {event['tool_name']} 결과 받음]")
            elif event["type"] == "text":
                print(f"\n에이전트: {event['content']}")
            elif event["type"] == "error":
                print(f"[❌ {event['message']}]")
