from typing import Dict, Any, Iterable
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.price import upsert_price_data as _upsert

# 인터페이스
class SQLAlchemyPriceRepository:
    async def upsert_price_data(self, db: AsyncSession, rows: Iterable[Dict[str, Any]]) -> int:
        return await _upsert(db, rows)