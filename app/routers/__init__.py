"""
컨트롤러 모듈

API 엔드포인트들을 정의합니다.
외부 HTTP 요청을 직접 받는 엔드포인트입니다.
요청을 받아 적절한 서비스로 라우팅합니다.
"""

from fastapi import APIRouter

from .auth import router as auth_router
from .price import router as price_router
from .strategy import router as strategy_router
from .ticker import router as ticker_router
from .user import router as user_router
from .tradingview import router as tradingview_router
from .paper_trading import router as paper_trading_router
from . import websocket

__all__ = [
    "user_router",
    "ticker_router",
    "auth_router",
    "price_router",
    "strategy_router",
    "tradingview_router",
    "paper_trading_router",
    "websocket",
]


def get_router(prefix: str):
    base_prefix = "/caps_lock/api"
    concat_prefix = "/".join([base_prefix, prefix])
    if concat_prefix[-1] == "/":
        concat_prefix = concat_prefix[:-1]
    router = APIRouter(prefix=concat_prefix, tags=[prefix])

    return router
