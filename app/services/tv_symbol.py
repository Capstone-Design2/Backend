from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ticker import TickerRepository
from app.schemas.tradingview import SearchItemOut
from app.utils.tv_format import build_symbol_meta_udf

class TVSymbolService:
    def __init__(self, t_repo: TickerRepository):
        self.t_repo = t_repo
    
    @staticmethod
    def _split_exchange(symbol: str):
        if ":" in symbol:
            ex, sym = symbol.split(":", 1)
            return ex, sym
        return None, symbol

    async def get_symbol_meta_udf(
        self, *, 
        symbol: str, 
        db: AsyncSession
    ) -> dict:
        tid = await self.t_repo.resolve_symbol_to_id(symbol, db=db)
        meta = await self.t_repo.get_symbol_meta(ticker_id=tid, db=db)
        return build_symbol_meta_udf(meta)

    async def search_udf(
        self,
        *,
        db: AsyncSession,
        query: str,
        limit: int = 30,
        exchange: Optional[str] = None,
    ) -> List[SearchItemOut]:
        rows = await self.t_repo.search(
            db,
            query=query,
            limit=limit,
            market=exchange,
        )

        out: List[SearchItemOut] = []
        for r in rows:
            ex = r.market or (exchange or "")  # 없는 경우 빈 문자열
            sym = r.symbol
            full_name = f"{ex}:{sym}" if ex else sym
            out.append(
                SearchItemOut(
                    symbol=sym,                      
                    full_name=full_name,
                    description=(r.company_name or r.symbol),
                    exchange=ex,
                    ticker=sym,                        
                    type="stock",                      
                )
            )
        return out
