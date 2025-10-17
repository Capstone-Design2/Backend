from fastapi import APIRouter


def get_router(prefix: str):
    """
    공통 API 라우터 생성 유틸리티

    Args:
        prefix (str): 엔드포인트의 마지막 경로명 (예: "user", "auth")

    Returns:
        APIRouter: /caps_lock/api/{prefix} 구조의 FastAPI 라우터
    """
    base_prefix = "/caps_lock/api"

    # 🔹 중복된 슬래시나 대문자 문제 방지
    prefix = prefix.strip("/").lower()

    # 🔹 경로 병합 ("/caps_lock/api/user" 형태로)
    full_prefix = f"{base_prefix}/{prefix}"

    # 🔹 라우터 객체 생성
    router = APIRouter(prefix=full_prefix, tags=[prefix])

    return router
