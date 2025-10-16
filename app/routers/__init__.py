"""
컨트롤러 모듈

API 엔드포인트들을 정의합니다.
요청을 받아 적절한 서비스로 라우팅합니다.
"""

from fastapi import APIRouter

from .user import router as user_router

__all__ = [
    "user_router",
]


def get_router(prefix: str):
    base_prefix = "/caps_lock/api"
    concat_prefix = "/".join([base_prefix, prefix])
    if concat_prefix[-1] == "/":
        concat_prefix = concat_prefix[:-1]
    router = APIRouter(prefix=concat_prefix, tags=[prefix])

    return router
