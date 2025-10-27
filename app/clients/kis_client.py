# app/clients/kis_client.py
from typing import Any
from app.services.kis_prices import KISPrices
from app.services.price import Period

class KISClientImpl:
    def __init__(self, inner: KISPrices | None = None):
        self.inner = inner or KISPrices()

    async def get_period_candles(
        self, code: str, start_ymd: str, end_ymd: str, *, period: Period
    ) -> list[dict[str, Any]]:
        return await self.inner.get_period_candles(code, start_ymd, end_ymd, period=period)

    async def get_intraday_by_date(
        self, code: str, *, date: str, unit: int | None = None
    ) -> list[dict[str, Any]]:
        # inner가 unit을 지원하지 않으면 무시하고 호출
        return await self.inner.get_intraday_by_date(code, date=date)  # unit 무시

    async def get_intraday_today(
        self, code: str, *, unit: int | None = None
    ) -> list[dict[str, Any]]:
        return await self.inner.get_intraday_today(code)  # unit 무시
