from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ticker import TickerService as _TickerService

class TickerClientImpl:
    def __init__(self, inner: _TickerService | None = None):
        self.inner = inner or _TickerService()

    async def load_kis_to_ticker_id(self, db: AsyncSession):
        return await self.inner.load_kis_to_ticker_id(db)

    async def resolve_one(self, db: AsyncSession, *, kis_code: str):
        return await self.inner.resolve_one(db, kis_code=kis_code)