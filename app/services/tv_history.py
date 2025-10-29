from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ticker import TickerRepository
from app.repositories.price import PriceRepository
from app.utils.tv_format import build_history_udf
from app.core.tradingview import RESOLUTION_TO_TIMEFRAME

class TVHistoryService:
    def __init__(self, t_repo: TickerRepository, p_repo: PriceRepository):
        self.t_repo = t_repo
        self.p_repo = p_repo

    async def get_history_udf(self, *, symbol: str, start_ts: int, end_ts: int,
                            resolution: str, adjusted: bool, db: AsyncSession) -> dict:
        timeframe = RESOLUTION_TO_TIMEFRAME.get(resolution)
        if not timeframe:
            raise ValueError(f"Unsupported resolution: {resolution}")

        ticker_id = await self.t_repo.resolve_symbol_to_id(symbol, db=db)
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        end_dt   = datetime.fromtimestamp(end_ts, tz=timezone.utc)

        price_data = await self.p_repo.get_price_data_front(
            ticker_id=ticker_id,
            start=start_dt,
            end=end_dt,
            timeframe=timeframe,
            adjusted=adjusted,
            db=db,
        )

        rows = []
        for p in price_data or []:
            if p.open is None or p.high is None or p.low is None or p.close is None:
                continue
            rows.append({
                "t": int(p.timestamp.timestamp()),
                "o": float(p.open),
                "h": float(p.high),
                "l": float(p.low),
                "c": float(p.close),
                "v": int(p.volume or 0),
            })
        # 오름차순 보장(필요 시)
        rows.sort(key=lambda r: r["t"])
        return build_history_udf(rows)
