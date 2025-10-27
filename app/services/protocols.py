from __future__ import annotations
from typing import Protocol, Dict, Any, Iterable
from sqlalchemy.ext.asyncio import AsyncSession

class KISClient(Protocol):
    async def get_period_candles(
        self, code: str, start_ymd: str, end_ymd: str, *, period: str
    ) -> list[dict[str, Any]]: ...
    
    async def get_intraday_by_date(
        self, code: str, *, date: str, unit: int | None = None
    ) -> list[dict[str, Any]]: ...
    
    async def get_intraday_today(
        self, code: str, *, unit: int | None = None
    ) -> list[dict[str, Any]]: ...

class TickerClient(Protocol):
    async def load_kis_to_ticker_id(self, db: AsyncSession) -> Dict[str, int]: ...
    async def resolve_one(self, db: AsyncSession, *, kis_code: str) -> tuple[int, str]: ...

class PriceRepository(Protocol):
    async def upsert_price_data(self, db: AsyncSession, rows: Iterable[Dict[str, Any]]) -> int: ...
