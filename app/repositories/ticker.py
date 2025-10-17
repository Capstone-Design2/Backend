from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
from app.models.ticker import Ticker

class TickerRepository:
    async def bulk_upsert_by_market_symbol(self, db: AsyncSession, rows):
        if not rows:
            return 0
        stmt = insert(Ticker).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Ticker.market, Ticker.symbol],
            set_={
                "kis_code": stmt.excluded.kis_code,
                "company_name": stmt.excluded.company_name,
                "isin": stmt.excluded.isin,
                "updated_at": func.now(),
            },
        )
        result = await db.execute(stmt)
        await db.commit()
        return getattr(result, "rowcount", 0) or 0
