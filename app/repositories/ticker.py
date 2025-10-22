from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def get_by_name(self, name: str, db: AsyncSession) -> Optional[Ticker]:
        """회사명으로 티커를 조회합니다. 없으면 None을 반환합니다."""
        stmt = select(Ticker).where(Ticker.company_name == name)
        result = await db.execute(stmt)
        return result.scalars().first()
