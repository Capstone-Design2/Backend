from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.protocols import KISClient, TickerClient, PriceRepository
from app.services.price import (
    Period,
    ingest_daily_range, 
    ingest_intraday_by_date, 
    ingest_intraday_today,
    ingest_one_stock_all as ingest_one_stock_all_uc
)

class PriceService:
    def __init__(self, kis: KISClient, ticker: TickerClient, repo: PriceRepository):
        self.kis = kis
        self.ticker = ticker
        self.repo = repo

    async def sync_daily_prices(
        self, db: AsyncSession, start_date: str, end_date: str, *, period: Period = "D"
    ) -> dict:
        kis_to_tid = await self.ticker.load_kis_to_ticker_id(db)
        count = await ingest_daily_range(
            db, self.kis, self.repo, kis_to_tid, kis_to_tid.keys(), start_date, end_date, period=period
        )
        await db.commit()
        return {"synced": count, "timeframe": "1D"}

    async def sync_intraday_by_date(self, db: AsyncSession, date: str, *, unit: int = 1) -> dict:
        kis_to_tid = await self.ticker.load_kis_to_ticker_id(db)
        count = await ingest_intraday_by_date(
            db, self.kis, self.repo, kis_to_tid, kis_to_tid.keys(), date, unit=unit
        )
        await db.commit()
        return {"synced": count, "unit": unit}

    async def sync_intraday_today(self, db: AsyncSession, *, unit: int = 1) -> dict:
        kis_to_tid = await self.ticker.load_kis_to_ticker_id(db)
        count = await ingest_intraday_today(
            db, self.kis, self.repo, kis_to_tid, kis_to_tid.keys(), unit=unit
        )
        await db.commit()
        return {"synced": count, "unit": unit}

    async def ingest_one_stock_all(
        self,
        db: AsyncSession,
        years: int,
        months: int,
        period: Period = "D",
    ) -> dict:
        return await ingest_one_stock_all_uc(
            db,
            kis=self.kis,
            repo=self.repo,
            ticker=self.ticker,
            years=years,
            months=months,
            period=period,
        )