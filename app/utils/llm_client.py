import asyncio
import os
from typing import Any, Optional

from google import genai
from google.genai.types import (GenerateContentConfig, GoogleSearch,
                                ThinkingConfig, Tool)


class GeminiClient:
    """Gemini API 클라이언트 클래스"""

    # 기본 키 + 최대 3개까지만 순환 (1→2→3→1)
    _api_keys: list[str] = [
        k.strip()
        for k in [
            os.getenv("GOOGLE_API_KEY"),
            os.getenv("GOOGLE_API_KEY_2"),
            # os.getenv("GOOGLE_API_KEY_3"),
        ]
        if k
    ]
    _api_key_index: int = 0
    _api_key: Optional[str] = _api_keys[0] if _api_keys else None
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

    @classmethod
    def _rotate_api_key(cls) -> bool:
        """429 발생 시 1→2→3→1 순환"""
        if not cls._api_keys:
            return False

        cls._api_key_index = (cls._api_key_index + 1) % len(cls._api_keys)
        next_key = cls._api_keys[cls._api_key_index]
        cls._change_api_key(next_key)
        print(
            f"[Gemini] 키 전환: {cls._api_key_index + 1}/{len(cls._api_keys)}번 키 사용"
        )
        return True

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        # 심플: code가 429이거나 메시지에 429가 포함될 때만 감지
        return getattr(exc, "code", None) == 429 or "429" in str(exc)

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

                if cls._is_rate_limit_error(e):
                    rotated = cls._rotate_api_key()
                    if rotated:
                        # 새 키로 바로 재시도
                        continue

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

        try:
            response = await cls._retry_generate(
                model=target_model,
                contents=contents,
                config=config,
                max_retries=max_retries,
            )
        except Exception as e:
            print(f"[Gemini] 에러 발생: {e}")
            raise RuntimeError("구조화된 JSON(parsed)을 얻지 못했습니다.")

        if getattr(response, "parsed", None) is None:
            # 디버깅을 위한 상세 정보 출력
            print(f"[Gemini] response 객체: {response}")
            print(
                f"[Gemini] response.text: {getattr(response, 'text', 'N/A')}")
            print(
                f"[Gemini] response.candidates: {getattr(response, 'candidates', 'N/A')}")
            if hasattr(response, 'candidates') and response.candidates:
                for i, candidate in enumerate(response.candidates):
                    print(
                        f"[Gemini] candidate[{i}].content: {getattr(candidate, 'content', 'N/A')}")
                    print(
                        f"[Gemini] candidate[{i}].finish_reason: {getattr(candidate, 'finish_reason', 'N/A')}")
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
    ):
        # LLM이 상태를 자연스럽게 이해하도록
        state_text = f"현재 전략 조건 상태: {session_state}"
        contents = [state_text, content]

        response = await cls.generate_structured_content(
            system_prompt=strategy_chat_system_prompt,
            response_schema=strategy_chat_response_schema,
            contents=contents,
            temperature=temperature,
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
                "buy_conditions": {
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
                "sell_conditions": {
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
                "trade_settings": {
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
                "buy_conditions",
                "sell_conditions",
                "trade_settings",
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

### 핵심 원칙
사용자로부터 4가지 필수 조건에 대한 구체적인 정보를 수집하여 각 조건의 filled 상태를 true로 만들고 description을 채워야 합니다.

**4가지 필수 조건:**

1. **indicators**: 사용할 기술적 지표 정의
   - 구조: [{"name": "지표별칭", "type": "지표타입", "params": {...}}]
   - 지원 타입과 params:
     * SMA (단순이동평균): {"length": 20}
     * EMA (지수이동평균): {"length": 20}
     * RSI: {"length": 14}
     * MACD: {"fast": 12, "slow": 26, "signal": 9}
     * BBANDS (볼린저밴드): {"length": 20, "std": 2}
     * ADX: {"length": 14}
     * ATR: {"length": 14}
     * STOCH: {"k": 14, "d": 3}
     * PRICE (가격): {}
   - 이 영역은 "지표 레지스트리"입니다. buy/sell 조건에서는 여기서 정의한 name을 기본으로 참조하되, 멀티컬럼 지표는 아래 컬럼 규칙을 따라 세부 컬럼을 지목할 수 있습니다.
   - pandas-ta 컬럼 네이밍 규칙 (name 접두사 + 기본 컬럼명):
     * SMA/EMA/RSI/ATR: 단일 시리즈 → 예: sma20
     * MACD: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9 → 예: macd.MACD_12_26_9
     * BBANDS: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0 → 예: bb.BBL_20_2.0
     * ADX: ADX_14, DMP_14, DMN_14 → 예: adx.ADX_14
     * STOCH: STOCHk_14_3_3, STOCHd_14_3_3 → 예: stoch.STOCHk_14_3_3
     * PRICE: close, open, high, low, volume (원시 OHLCV는 별도 접두사 없이 바로 사용 가능)
   - params는 pandas-ta 인자명을 그대로 사용합니다(모르면 수치/파라미터를 재질문). 필요 시 사용자가 말한 "기간/윈도우"를 length 등으로 매핑해 주세요.

2. **buy_conditions**: 매수 진입 조건
   - 구조: {"all": [...]} 또는 {"any": [...]}
   - all: 모든 조건 충족 필요 (AND)
   - any: 하나만 충족 필요 (OR)
   - 각 조건: {"indicator1": "...", "operator": "...", "indicator2": "...", ["indicator3": "..."], ["lookback_period": N]}
   - indicator1/2/3는 반드시
     * indicators에서 정의한 name (단일 시리즈) 또는
     * 멀티컬럼 지표의 컬럼명(name.기본컬럼, 예: macd.MACD_12_26_9, bb.BBL_20_2.0, adx.ADX_14, stoch.STOCHk_14_3_3) 또는
     * 원시 OHLCV 컬럼(close/open/high/low/volume)
     중 하나여야 합니다. 새 지표를 조건에서 즉석 생성하지 말고, 필요하면 indicators에 먼저 정의하도록 요청하세요.
   - 지원 연산자 (14개):
     * 기본 비교: is_above, is_below, is_above_or_equal, is_below_or_equal, equals, not_equals
     * 크로스: crosses_above, crosses_below
     * 범위 (indicator3 필요): between, outside
     * 변화율 (lookback_period 필요): percent_change_above, percent_change_below
     * 연속 (lookback_period 필요): consecutive_above, consecutive_below

3. **sell_conditions**: 매도 청산 조건
   - buy_conditions와 완전히 동일한 구조
   - 위의 indicator 참조 규칙을 동일하게 적용합니다 (등록된 지표 이름, 멀티컬럼 접두사, OHLCV만 사용).

4. **trade_settings**: 주문 시 사용할 자본 비율
   - 예: "100%", "50%" 등
   - 사용자 미지정 시 빈 문자열("") 가능

### 사용자 자율권 위임 금지 규칙
사용자가 다음과 같은 의미의 발화를 할 경우:
"알아서 해줘", "추천해줘", "적당히 만들어줘", "네가 정해", "임의로 만들어줘",
"맡길게", "적당히 해줘", "니 마음대로 해", "적당히 채워", 그 외 AI에게 자율권을 넘기는 문장

→ 절대로 임의 추론, 임의 생성, 추천을 하지 않는다.
→ conditions의 filled나 description을 절대로 임의로 변경하지 않는다.
→ strategy를 절대로 생성하지 않는다.
→ status는 "chat" 또는 상황에 따라 "in_progress"로 유지하며,
   사용자에게 구체적인 전략 조건을 다시 요구하는 reply만 제공한다.

### 전략 생성 조건
모든 조건(indicators, buy_conditions, sell_conditions, trade_settings)이 filled=true일 때에만
status="complete"를 설정하고 strategy를 생성할 수 있다.

그 외의 경우:
- 추측으로 조건을 채우지 않는다.
- 조건을 AI가 작성하지 않는다.
- strategy를 생성하지 않는다.

### 상태 처리 규칙
1. chat: 일반 대화 → conditions는 그대로 유지
2. in_progress: 일부 조건만 충족 → 부족한 부분 질문
3. complete: 모든 filled=true → strategy에 최종 전략 JSON 생성

### 최종 strategy JSON 구조 예시

**골든크로스 전략 예시:**
{
  "indicators": [
    {"name": "sma20", "type": "SMA", "params": {"length": 20}},
    {"name": "sma60", "type": "SMA", "params": {"length": 60}},
    {"name": "rsi14", "type": "RSI", "params": {"length": 14}}
  ],
  "buy_conditions": {
    "all": [
      {"indicator1": "sma20", "operator": "crosses_above", "indicator2": "sma60"},
      {"indicator1": "rsi14", "operator": "is_below", "indicator2": "70"}
    ]
  },
  "sell_conditions": {
    "any": [
      {"indicator1": "sma20", "operator": "crosses_below", "indicator2": "sma60"},
      {"indicator1": "rsi14", "operator": "is_above", "indicator2": "70"}
    ]
  },
  "trade_settings": "100%"
}

### 자율권 위임 발화 대응 예시
사용자: "그냥 너가 다 알아서 만들어줘."
→ reply: "전략 요소를 임의로 결정할 수 없습니다. 원하는 지표나 진입/청산 조건을 구체적으로 알려주세요."
→ status="chat"
→ conditions: 변화 없음
→ strategy=null

### 중요: JSON 출력 형식
반드시 제공된 JSON 스키마를 정확히 따라야 합니다. 
- status는 "chat", "in_progress", "complete" 중 하나
- reply는 사용자에게 보낼 메시지 문자열
- conditions는 4개의 객체 (indicators, buy_conditions, sell_conditions, trade_settings)를 포함
- 각 condition 객체는 filled(boolean)와 description(string 또는 null)을 포함
- strategy는 문자열(JSON 형식) 또는 null
"""
