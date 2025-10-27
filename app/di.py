from __future__ import annotations
from app.services.price_service import PriceService
from app.clients.kis_client import KISClientImpl
from app.clients.ticker_client import TickerClientImpl
from app.repositories.price_repository import SQLAlchemyPriceRepository

# 의존성 주입
def get_price_service() -> PriceService:
    return PriceService(
        kis=KISClientImpl(),
        ticker=TickerClientImpl(),
        repo=SQLAlchemyPriceRepository(),
    )