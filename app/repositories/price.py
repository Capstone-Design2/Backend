from typing import Iterable, List, Dict, Any
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from app.models.price_data import PriceData

def _to_decimal(x) -> Decimal | None:
    if x in (None, ""):
        return None
    return Decimal(str(x))

async def upsert_price_data(db: AsyncSession, rows: Iterable[Dict[str, Any]]) -> int:
    payload: List[Dict[str, Any]] = []
    for r in rows:
        payload.append({
            "ticker_id": r["ticker_id"],
            "timestamp": r["timestamp"],
            "timeframe": r["timeframe"],
            "open":  _to_decimal(r.get("open")),
            "high":  _to_decimal(r.get("high")),
            "low":   _to_decimal(r.get("low")),
            "close": _to_decimal(r.get("close")),
            "volume": int(r["volume"]) if r.get("volume") not in (None, "") else None,
            "source": r.get("source", "KIS"),
            "is_adjusted": bool(r.get("is_adjusted", False)),
        })

    if not payload:
        return 0

    # insert 객체 생성
    insert_stmt = insert(PriceData).values(payload)

    # excluded 참조는 insert_stmt에서 가져옴
    update_dict = {
        "open": insert_stmt.excluded.open,
        "high": insert_stmt.excluded.high,
        "low": insert_stmt.excluded.low,
        "close": insert_stmt.excluded.close,
        "volume": insert_stmt.excluded.volume,
        "is_adjusted": insert_stmt.excluded.is_adjusted,
        "updated_at": func.now(),
    }

    # 최종 statement 생성
    stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_price_ticker_ts_tf_source",
        set_=update_dict,
    )
    
    await db.execute(stmt)
    return len(payload)
