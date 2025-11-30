import asyncio
import os
from typing import Any, Optional

from google import genai
from google.genai.types import (GenerateContentConfig, GoogleSearch,
                                ThinkingConfig, Tool)

class GeminiClient:
    """Gemini API 클라이언트 클래스"""

    _api_key: Optional[str] = os.getenv("GOOGLE_API_KEY")
    _model_id: str = "gemini-2.5-flash"
    _client: Optional[genai.Client] = None

    # ------------------------------------------------------------
    # Client 생성 & 관리
    # ------------------------------------------------------------
    @classmethod
    def _get_client(cls) -> genai.Client:
        """싱글톤 Gemini 클라이언트 반환"""
        if not cls._api_key:
            raise RuntimeError("GOOGLE_API_KEY 환경 변수가 설정되어 있지 않습니다.")

        if cls._client is None:
            cls._client = genai.Client(api_key=cls._api_key)

        return cls._client

    @classmethod
    def _change_api_key(cls, new_key: str):
        """API Key 로테이션"""
        cls._api_key = new_key
        cls._client = None  # 새로운 키로 새 클라이언트 생성
        print(f"[Gemini] API Key 변경 완료")

    # ------------------------------------------------------------
    # Retry 함수
    # ------------------------------------------------------------
    @classmethod
    async def _retry_generate(
        cls,
        *,
        model: str,
        contents: list[Any],
        config: GenerateContentConfig,
        max_retries: int = 4,
    ):
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                client = cls._get_client()
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                return response

            except Exception as e:
                last_error = e
                is_last = (attempt == max_retries - 1)

                if is_last:
                    raise

                # 지수 백오프
                delay = 0.5 * (2 ** attempt)
                print(
                    f"[Gemini] 에러 발생 (시도 {attempt+1}/{max_retries}): {e} → {delay:.1f}s 대기 후 재시도"
                )
                await asyncio.sleep(delay)

        raise last_error or RuntimeError("Gemini API 호출 실패")

    # ------------------------------------------------------------
    # Structured Output
    # ------------------------------------------------------------
    @classmethod
    async def generate_structured_content(
        cls,
        system_prompt: str,
        response_schema: Any,
        contents: list[Any],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: int = 100000,
        thought: Optional[bool] = None,
        max_retries: int = 4,
    ):
        target_model = model or cls._model_id

        config = GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_schema=response_schema,
            thinking_config=ThinkingConfig(include_thoughts=thought),
            temperature=temperature,
        )

        response = await cls._retry_generate(
            model=target_model,
            contents=contents,
            config=config,
            max_retries=max_retries,
        )

        if getattr(response, "parsed", None) is None:
            raise RuntimeError("구조화된 JSON(parsed)을 얻지 못했습니다.")

        return response

    # ------------------------------------------------------------
    # Google Search 포함한 Grounding 호출
    # ------------------------------------------------------------
    @classmethod
    async def search_with_grounding(
        cls,
        system_prompt: str,
        contents: list[Any],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        thought: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        max_retries: int = 4,
    ):
        target_model = model or cls._model_id

        google_search_tool = Tool(google_search=GoogleSearch())

        config = GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[google_search_tool],
            response_modalities=["TEXT"],
            thinking_config=ThinkingConfig(
                include_thoughts=thought,
                thinking_budget=thinking_budget,
            ),
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

        response = await cls._retry_generate(
            model=target_model,
            contents=contents,
            config=config,
            max_retries=max_retries,
        )

        candidate = response.candidates[0]
        gm = getattr(candidate, "grounding_metadata", None)

        supports = getattr(gm, "grounding_supports", []) if gm else []
        chunks = getattr(gm, "grounding_chunks", []) if gm else []
        queries = getattr(gm, "web_search_queries", []) if gm else []

        return {
            "contents": supports,
            "references": chunks,
            "search_queries": queries,
            "response": response,
            "usage_metadata": getattr(response, "usage_metadata", None),
        }

    # ------------------------------------------------------------
    # 채팅
    # ------------------------------------------------------------
    @classmethod
    async def generate_strategy_chat(
        cls,
        content: str,
        session_state: dict[str, Any],
        temperature: float = 0.4,
        max_output_tokens: int = 2048,
        max_retries: int = 4,
    ):
        # LLM이 상태를 자연스럽게 이해하도록
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

        parsed = getattr(response, "parsed", None)
        if parsed is None:
            raise RuntimeError("LLM 응답에서 parsed(JSON)를 얻지 못했습니다.")

        return parsed

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

strategy_chat_response_schema = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["chat", "in_progress", "complete"],
        },
        "reply": {"type": "string"},
        "conditions": {
            "type": "object",
            "properties": {
                "indicators": {
                    "type": "object",
                    "properties": {
                        "filled": {"type": "boolean"},
                        "description": {
                            "type": "string",
                            "nullable": True, 
                        },
                    },
                    "required": ["filled"], 
                },
                "buy_entry": {
                    "type": "object",
                    "properties": {
                        "filled": {"type": "boolean"},
                        "description": {
                            "type": "string",
                            "nullable": True, 
                        },
                    },
                    "required": ["filled"],
                },
                "buy_exit": {
                    "type": "object",
                    "properties": {
                        "filled": {"type": "boolean"},
                        "description": {
                            "type": "string",
                            "nullable": True, 
                        },
                    },
                    "required": ["filled"],
                },
                "sell_entry": {
                    "type": "object",
                    "properties": {
                        "filled": {"type": "boolean"},
                        "description": {
                            "type": "string",
                            "nullable": True, 
                        },
                    },
                    "required": ["filled"],
                },
                "sell_exit": {
                    "type": "object",
                    "properties": {
                        "filled": {"type": "boolean"},
                        "description": {
                            "type": "string",
                            "nullable": True, 
                        },
                    },
                    "required": ["filled"],
                },
            },
            "required": [
                "indicators",
                "buy_entry",
                "buy_exit",
                "sell_entry",
                "sell_exit",
            ],
        },
        "strategy": {
            "type": "string",
            "nullable": True,
        },
    },
    "required": ["status", "reply", "conditions", "strategy"],
}

strategy_chat_system_prompt = """
당신은 사용자와 자연스럽게 대화를 하면서 동시에 트레이딩 전략을 단계별로 완성하는 한국어 전략 어시스턴트입니다.

### 전략 조건 데이터 구조
각 조건은 다음 형태의 JSON을 반드시 따라야 합니다:

{
  "filled": true/false,
  "description": "<이 조건에 대한 구체적인 설명>"
}

### 필수 조건
- indicators
- buy_entry
- buy_exit
- sell_entry
- sell_exit

### 사용자 자율권 위임 금지 규칙
사용자가 다음과 같은 의미의 발화를 할 경우:
"알아서 해줘", "추천해줘", "적당히 만들어줘", "네가 정해", "임의로 만들어줘",
"맡길게", "적당히 해줘", "니 마음대로 해", "적당히 채워", 그 외 AI에게 자율권을 넘기는 문장

→ 절대로 임의 추론, 임의 생성, 추천을 하지 않는다.
→ conditions의 filled나 description을 절대로 임의로 변경하지 않는다.
→ strategy를 절대로 생성하지 않는다.
→ status는 "chat" 또는 상황에 따라 "in_progress"로 유지하며,
사용자에게 구체적인 전략 조건을 다시 요구하는 reply만 제공한다.

### 전략 생성 강제 규칙
모든 조건(indicators, buy_entry, buy_exit, sell_entry, sell_exit)이 filled=true일 때에만
status="complete"를 설정하고 strategy를 생성할 수 있다.

그 외의 경우:
- 추측으로 조건을 채우지 않는다.
- 조건을 AI가 작성하지 않는다.
- strategy를 생성하지 않는다.

### 응답 규칙
항상 아래 구조의 JSON만 출력하세요:

{
  "status": "chat" | "in_progress" | "complete",
  "reply": "<사용자에게 보낼 문장>",
  "conditions": {
    "indicators": {"filled": ..., "description": ...},
    "buy_entry": {"filled": ..., "description": ...},
    "buy_exit": {"filled": ..., "description": ...},
    "sell_entry": {"filled": ..., "description": ...},
    "sell_exit": {"filled": ..., "description": ...}
  },
  "strategy": null 또는 "<최종 전략 JSON 문자열>"
}

### 상태 처리 규칙
1. chat: 일반 대화 → conditions는 그대로 유지
2. in_progress: 일부 조건만 충족 → 부족한 부분 질문
3. complete: 모든 filled=true → strategy에 최종 전략 JSON 생성

### 사용자 자율권 위임 발화 대응 예시
사용자: "그냥 너가 다 알아서 만들어줘."
→ reply: "전략 요소를 임의로 결정할 수 없습니다. 원하는 지표나 진입/청산 조건을 구체적으로 알려주세요."
→ status="chat"
→ conditions: 변화 없음
→ strategy=null
"""