import asyncio
import os

from google import genai
from google.genai.types import (GenerateContentConfig, GoogleSearch,
                                ThinkingConfig, Tool)


class GeminiClient:
    """Gemini API 클라이언트 클래스"""

    _api_key = os.getenv("GOOGLE_API_KEY")

    _model_id = "gemini-2.5-flash"

    @classmethod
    def _create_client(cls):
        """새로운 Gemini 클라이언트 인스턴스 생성"""
        return genai.Client(
            api_key=cls._api_key,
        )

    @classmethod
    def _change_api_key(cls):
        # TODO: API Key 변경 로직 추가
        print(f"Gemini API Key 변경 완료:")

    @classmethod
    async def generate_structured_content(  cls, system_prompt, response_schema, contents,
                                            model=None,
                                            temperature=None,
                                            max_output_tokens=100000,
                                            thought=None,
                                            max_retries=4
    ):
        last_error = None

        for attempt in range(max_retries):
            try:
                client = cls._create_client()
                response = await client.aio.models.generate_content(
                    model=model if model else cls._model_id,
                    contents=contents,
                    config=GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=max_output_tokens,
                        response_mime_type="application/json",
                        response_schema=response_schema,
                        thinking_config=ThinkingConfig(
                            include_thoughts=thought,
                        ),
                        temperature=temperature
                    )
                )

                if getattr(response, "parsed", None):
                    return response

                await asyncio.sleep(1)

            except Exception as e:
                print(f"Gemini API 호출 중 에러 발생 (시도 {attempt + 1}/{max_retries}): {e}")
                last_error = e
                if attempt == max_retries - 1:
                    raise e

        # 여기까지 오면 parsed가 한 번도 채워지지 않은 케이스
        if last_error:
            raise last_error
        raise RuntimeError("Gemini API 호출은 성공했지만 parsed 응답을 얻지 못했습니다.")

    @classmethod
    async def search_with_grounding(cls, system_prompt, contents,
                                    model=None,
                                    temperature=None,
                                    max_output_tokens=None,
                                    thought=None,
                                    thinking_budget=None,
                                    max_retries=4):
        """웹 검색을 포함한 콘텐츠 생성 (기존 gemini_search 함수 대체)"""

        for attempt in range(max_retries):
            try:
                # 매번 새로운 클라이언트 생성
                client = cls._create_client()

                google_search_tool = Tool(
                    google_search=GoogleSearch()
                )

                response = await client.aio.models.generate_content(
                    model=model if model else cls._model_id,
                    contents=contents,
                    config=GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=[google_search_tool],
                        response_modalities=["TEXT"],
                        thinking_config=ThinkingConfig(
                            include_thoughts=thought,
                            thinking_budget=thinking_budget
                        ),
                        max_output_tokens=max_output_tokens,
                        temperature=temperature,
                    )
                )

                contents = response.candidates[0].grounding_metadata.grounding_supports
                references = response.candidates[0].grounding_metadata.grounding_chunks
                search_queries = response.candidates[0].grounding_metadata.web_search_queries

                res = {"contents": contents, "references": references,
                       "search_queries": search_queries, "response": response}
                return res

            except Exception as e:
                print(
                    f"Gemini 검색 API 호출 중 에러 발생 (시도 {attempt + 1}/{max_retries}): {e}")

                if attempt == max_retries - 1:  # 마지막 시도
                    raise e

                if "429" in str(e):
                    ...
                    # TODO : API Key 변경 로직 추가
                    # cls._change_api_key()
    
    @classmethod
    async def generate_strategy_chat(
        cls,
        content: str,
        session_state: dict,
        temperature: float = 0.4,
        max_output_tokens: int = 2048,
        max_retries: int = 4,
    ):
        state_text = f"현재 전략 조건 상태: {session_state}"
        contents = [state_text, content]

        response = await cls.generate_structured_content(
            system_prompt=strategy_chat_system_prompt,
            response_schema=strategy_chat_response_schema,
            contents=contents,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            max_retries=max_retries,
        )

        if response is None or getattr(response, "parsed", None) is None:
            # 여기서 바로 에러를 명시적으로 터뜨리게
            raise RuntimeError("LLM 응답을 구조화하지 못했습니다. response.parsed가 비어 있습니다.")

        return response.parsed


def model_dumps(contents: list):
    return [c.model_dump() for c in contents]


def calculate_gemini_cost(usage_metadata, search_queries: list = [], wd_rate=1470):
    if search_queries:
        search_api_cost = 35/1000
    else:
        search_api_cost = 0
    input_token_cost = usage_metadata.prompt_token_count * 0.15/1000000
    output_token_cost = usage_metadata.candidates_token_count * 3.5/1000000
    total_cost = (search_api_cost + input_token_cost +
                  output_token_cost)*wd_rate
    return total_cost


test_system_prompt = """
            You are a helpful assistant that can help with trading strategies.
            You are given a trading strategy and a user message.
            You need to respond to the user message based on the trading strategy.
            """

test_response_schema = {
    "type": "object",
    "properties": {
        "indicators": {
            "type": "array",
            "description": "전략에서 사용하는 지표 목록",
            "items": {
                "type": "object",
                "description": "지표 하나 (형식은 자유)",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "지표를 표현하는 문자열 또는 JSON 문자열"
                    }
                },
            }
        },
        "buy_entry": {
            "type": "array",
            "description": "매수 진입 조건 리스트",
            "items": {
                "type": "object",
                "description": "매수 진입 조건 하나 (형식은 자유)",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "조건을 표현하는 문자열 또는 JSON 문자열"
                    }
                },
            }
        },
        "buy_exit": {
            "type": "array",
            "description": "매수 청산 조건 리스트",
            "items": {
                "type": "object",
                "description": "매수 청산 조건 하나 (형식은 자유)",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "조건을 표현하는 문자열 또는 JSON 문자열"
                    }
                },
            }
        },
        "sell_entry": {
            "type": "array",
            "description": "매도 진입 조건 리스트",
            "items": {
                "type": "object",
                "description": "매도 진입 조건 하나 (형식은 자유)",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "조건을 표현하는 문자열 또는 JSON 문자열"
                    }
                },
            }
        },
        "sell_exit": {
            "type": "array",
            "description": "매도 청산 조건 리스트",
            "items": {
                "type": "object",
                "description": "매도 청산 조건 하나 (형식은 자유)",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "조건을 표현하는 문자열 또는 JSON 문자열"
                    }
                },
            }
        }
    },
    "required": [
        "indicators",
        "buy_entry",
        "buy_exit",
        "sell_entry",
        "sell_exit"
    ],
}

strategy_chat_response_schema = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["chat", "in_progress", "complete"]
        },
        "reply": {"type": "string"},
        "conditions": {
            "type": "object",
            "properties": {
                "indicators": {"type": "boolean"},
                "buy_entry": {"type": "boolean"},
                "buy_exit": {"type": "boolean"},
                "sell_entry": {"type": "boolean"},
                "sell_exit": {"type": "boolean"},
            },
            "required": [
                "indicators",
                "buy_entry",
                "buy_exit",
                "sell_entry",
                "sell_exit"
            ]
        },
        "strategy": {
            "type": "string",
            "nullable": True,
            "description": "완성된 전략 JSON 문자열"
        }
    },
    "required": ["status", "reply", "conditions", "strategy"]
}


strategy_chat_system_prompt = """
당신은 사용자와 자연스럽게 대화를 하면서 동시에 트레이딩 전략을 단계별로 완성해주는 한국어 전략 어시스턴트입니다.

### 당신의 책임
1. 사용자가 단순 인사나 일상 대화를 하면 자연스럽게 응답해야 합니다.
2. 하지만 매 메시지마다, 사용자의 발화가 아래 전략 요소들 중 무엇을 채우는지 판단해야 합니다:
   - indicators : 어떤 지표(ex. 이동평균선, RSI, MACD 등)가 사용되는가
   - buy_entry  : 매수 진입 조건
   - buy_exit   : 매수 청산 조건(익절/손절 등)
   - sell_entry : 매도 진입 조건
   - sell_exit  : 매도 청산 조건

### 응답 규칙
당신의 응답은 항상 JSON 형식이어야 하며, 다음 중 하나의 status를 포함해야 합니다:

1. "chat"
   - 일상 대화나 인사말 위주일 때
   - conditions는 기존 상태를 그대로 유지
   - strategy는 null

2. "in_progress"
   - 전략 조건 중 일부만 충족된 상태
   - 부족한 조건이 무엇인지 자연스럽게 질문하거나 추가 정보를 요구하세요.
   - strategy는 null

3. "complete"
   - 모든 조건(indicators, buy_entry, buy_exit, sell_entry, sell_exit)이 모두 True일 때
   - strategy 필드에 최종 전략 JSON을 생성하여 포함하세요.
   - reply에는 "전략 조건이 모두 충족되었습니다. 아래 전략으로 생성할까요?" 와 같은 문장을 넣으세요.

### JSON Output Format
아래 형식을 반드시 지키세요:

{
  "status": "chat" | "in_progress" | "complete",
  "reply": "<사용자에게 보낼 자연스러운 문장>",
  "conditions": {
    "indicators": true/false,
    "buy_entry": true/false,
    "buy_exit": true/false,
    "sell_entry": true/false,
    "sell_exit": true/false
  },
  "strategy": null 또는 { ... 전략 JSON ... }
}

절대로 JSON 밖에 텍스트를 섞지 마십시오.
"""
