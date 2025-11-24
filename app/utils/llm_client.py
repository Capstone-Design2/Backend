import asyncio
import os

from google import genai
from google.genai.types import (GenerateContentConfig, GoogleSearch,
                                ThinkingConfig, Tool)


class GeminiClient:
    """Gemini API 클라이언트 클래스"""

    _api_key = os.getenv(
        "GOOGLE_API_KEY", "AIzaSyBhYU0D1rrywjnxPRk2NxQO43j3IJ233b8")

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
    async def generate_structured_content(cls, system_prompt, response_schema, contents,
                                          model=None,
                                          temperature=None,
                                          max_output_tokens=100000,
                                          thought=None,
                                          thinking_budget=None,
                                          max_retries=4):
        """구조화된 콘텐츠 생성 (기존 gemini_structed 함수 대체)"""

        for attempt in range(max_retries):
            try:
                # 매번 새로운 클라이언트 생성
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
                            thinking_budget=thinking_budget
                        ),
                        temperature=temperature
                    )
                )
                if response.parsed:
                    return response

                await asyncio.sleep(1)

            except Exception as e:
                print(
                    f"Gemini API 호출 중 에러 발생 (시도 {attempt + 1}/{max_retries}): {e}")

                if attempt == max_retries - 1:  # 마지막 시도
                    raise e

                if "429" in str(e):
                    ...
                    # TODO : API Key 변경 로직 추가
                    # cls._change_api_key()

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
