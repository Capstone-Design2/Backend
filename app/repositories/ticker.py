from typing import Any, Dict, List, Optional, cast

from sqlalchemy import func, select, case, or_, asc, desc
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticker import Ticker

class TickerRepository:
    async def bulk_upsert_by_market_symbol(self, db: AsyncSession, rows):
        if not rows:
            return 0
        stmt = insert(Ticker).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tickers_market_symbol",
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
    
    async def resolve_symbol_to_id(self, symbol: str, db: AsyncSession) -> int:
        s = symbol.strip()
        col = Ticker.__table__.c.symbol

        # 1) 정확 일치
        res = await db.execute(select(Ticker).where(col == s))
        row: Optional[Ticker] = cast(Optional[Ticker], res.scalar_one_or_none())
        if row is None:
            # 2) 대소문자 무시 일치
            res2 = await db.execute(select(Ticker).where(func.lower(col) == s.lower()))
            row = cast(Optional[Ticker], res2.scalar_one_or_none())
            if row is None: 
                # 3) 부분 일치
                res3 = await db.execute(select(Ticker).where(col.contains(s)))
                row = cast(Optional[Ticker], res3.scalar_one_or_none())
                if row is None:
                    # 4) 대소문자 무시 부분 일치 (Postgres)
                    res4 = await db.execute(
                        select(Ticker).where(col.ilike(f"%{s}%"))
                    )
                    row = cast(Optional[Ticker], res4.scalar_one_or_none())
                    if row is None:
                        raise ValueError(f"Unknown symbol: {symbol}")

        # 여기서 row: Ticker
        tid = row.ticker_id
        if tid is None:
            # DB 무결성상 거의 없겠지만, 타입 내로잉을 위해 분리
            raise ValueError(f"ticker_id is NULL for symbol: {row.symbol}")

        return tid

    async def get_symbol_by_id(self, ticker_id: int, db: AsyncSession) -> Ticker:
        stmt = select(Ticker).where(Ticker.ticker_id == ticker_id)
        res = await db.execute(stmt)
        row: Optional[Ticker] = res.scalar_one_or_none()
        if not row:
            raise ValueError(f"Unknown ticker_id: {ticker_id}")
        return row

    async def get_symbol_meta(self, ticker_id: int, db: AsyncSession) -> Dict[str, Any]:
        tk = await self.get_symbol_by_id(ticker_id, db=db)

        MARKET_META = {
            "KOSPI":  {"timezone": "Asia/Seoul", "session": "0900-1530", "type": "stock"},
            "KOSDAQ": {"timezone": "Asia/Seoul", "session": "0900-1530", "type": "stock"},
            "KONEX":  {"timezone": "Asia/Seoul", "session": "0900-1530", "type": "stock"},
            "ETF":    {"timezone": "Asia/Seoul", "session": "0900-1530", "type": "fund"},
        }
        m = MARKET_META.get(tk.market, {"timezone": "UTC", "session": "0000-0000", "type": "stock"})

        PRICE_DECIMALS_DEFAULT = 6
        meta = {
            "symbol": tk.symbol,
            "description": tk.company_name or tk.symbol,
            "exchange": tk.market,
            "type": m["type"],
            "currency": tk.currency or "KRW",
            "session": m["session"],
            "timezone": m["timezone"],
            "price_decimals": PRICE_DECIMALS_DEFAULT,
            "lot": 1,
            "minmov": 1,
        }
        return meta
    
    async def search(self,db: AsyncSession,*,query: str,limit: int = 30,market: Optional[str] = None) -> List[Ticker]:
        q = query.strip()
        col_symbol = Ticker.__table__.c.symbol
        col_name = Ticker.__table__.c.company_name
        col_isin = Ticker.__table__.c.isin
        col_kis = Ticker.__table__.c.kis_code

        exact = case(
            (
                or_(
                    col_symbol.ilike(q),
                    col_name.ilike(q),
                    col_isin.ilike(q),
                    col_kis.ilike(q),
                ),
                3,
            ),
            else_=0,
        )
        
        prefix = case(
            (
                or_(
                    col_symbol.ilike(f"{q}%"),
                    col_name.ilike(f"{q}%"),
                ),
                2,
            ),
            else_=0,
        )
        
        contains = case(
            (
                or_(
                    col_symbol.ilike(f"%{q}%"),
                    col_name.ilike(f"%{q}%"),
                    col_isin.ilike(f"%{q}%"),
                    col_kis.ilike(f"%{q}%"),
                ),
                1,
            ),
            else_=0,
        )

        score = exact + prefix + contains

        # 기본 쿼리
        stmt = select(Ticker).where(
            or_(
                col_symbol.ilike(f"{q}%"),
                col_name.ilike(f"{q}%"),
                col_symbol.ilike(f"%{q}%"),
                col_name.ilike(f"%{q}%"),
                col_isin.ilike(f"%{q}%"),
                col_kis.ilike(f"%{q}%"),
            )
        )


        if market:
            stmt = stmt.where(Ticker.__table__.c.market == market)

        stmt = stmt.order_by(desc(score), asc(col_symbol)).limit(limit)

        res = await db.execute(stmt)
        return res.scalars().all()
