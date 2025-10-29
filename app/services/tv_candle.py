from datetime import datetime, timezone
from app.repositories.price import PriceRepository
from app.core.tradingview import RESOLUTION_TO_TIMEFRAME

class GetCandles:
    def __init__(self, repo: PriceRepository):
        self.repo = repo
        
    async def execute(
        self,
        *,
        ticker_id: int,
        start_ts: int,
        end_ts: int,
        resolution: str,
        adjusted: bool,
        db,
    ):
        timeframe = RESOLUTION_TO_TIMEFRAME.get(resolution)
        if not timeframe:
            raise ValueError(f"Unsupported resolution: {resolution}")

        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)

        price_data = await self.repo.get_price_data_front(
            ticker_id=ticker_id,
            start=start_dt,
            end=end_dt,
            timeframe=timeframe,
            adjusted=adjusted,
            db=db,
        )

        if not price_data:
            return {"s": "no_data"}
        
        t: list[int] = []
        o: list[float] = []
        h: list[float] = []
        l: list[float] = []
        c: list[float] = []
        v: list[int]   = []

        for p in price_data:
            if p.open is None or p.high is None or p.low is None or p.close is None:
                continue

            ts = int(p.timestamp.timestamp())

            t.append(ts)
            o.append(float(p.open))
            h.append(float(p.high))
            l.append(float(p.low))
            c.append(float(p.close))
            v.append(int(p.volume or 0))
            
        if not t:
            return {"s": "no_data"}
        
        return {"s": "ok", "t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
