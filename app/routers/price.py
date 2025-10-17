from typing import Annotated
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.utils.router import get_router
from app.services.ticker import TickerService
from app.services.kis_prices import KISPrices

from app.services.price import (
    ingest_daily_range,
    ingest_intraday_by_date,
    ingest_intraday_today,
    TF_FROM_UNIT,   # Mapping[Unit, TF]
    Unit,           # Literal[1, 5, 15, 30, 60]
    Period,         # Literal["D","W","M","Y"]
)

router = get_router("price")

@router.post(
    "/daily",
    summary="국내주식 일별 시세 동기화 (KIS)",
    description="""
    지정된 기간 동안의 일봉(OHLCV) 데이터를 수집하고 price_data 테이블에 upsert합니다.
    """,
)
async def sync_daily_prices(
    db: Annotated[AsyncSession, Depends(get_session)],  
    start_date: Annotated[str, Query(description="YYYYMMDD")] = ...,
    end_date:   Annotated[str, Query(description="YYYYMMDD")] = ...,
):
    tsvc = TickerService()
    kis_to_tid = await tsvc.load_kis_to_ticker_id(db)
    kis = KISPrices()

    period: Period = "D"
    count = await ingest_daily_range(
        db, kis, kis_to_tid, kis_to_tid.keys(), start_date, end_date, period=period
    )
    await db.commit()
    return {"synced": count, "timeframe": "1D"}


@router.post(
    "/intraday/by-date",
    summary="국내주식 과거 분봉 시세 동기화 (KIS)",
    description="""
    지정된 날짜(YYYYMMDD)의 과거 분봉 데이터를 수집하고 price_data에 upsert합니다.
    """,
)
async def sync_intraday_by_date(
    db: Annotated[AsyncSession, Depends(get_session)],
    date: Annotated[str, Query(description="YYYYMMDD")] = ...,
    unit: Annotated[Unit, Query(description="분 단위 (1,5,15,30,60)")] = 1,
):
    tsvc = TickerService()
    kis_to_tid = await tsvc.load_kis_to_ticker_id(db)
    kis = KISPrices()

    count = await ingest_intraday_by_date(
        db, kis, kis_to_tid, kis_to_tid.keys(), date, unit=unit
    )
    await db.commit()
    return {"synced": count, "timeframe": TF_FROM_UNIT[unit]}


@router.post(
    "/intraday/today",
    summary="국내주식 당일 분봉 시세 동기화 (KIS)",
    description="""
    현재 거래일의 실시간 분봉 데이터를 수집하고 price_data에 upsert합니다.
    """,
)
async def sync_intraday_today(
    
    db: Annotated[AsyncSession, Depends(get_session)],  
    unit: Annotated[Unit, Query(description="분 단위 (1,5,15,30,60)")] = 1,
):
    tsvc = TickerService()
    kis_to_tid = await tsvc.load_kis_to_ticker_id(db)
    kis = KISPrices()

    count = await ingest_intraday_today(
        db, kis, kis_to_tid, kis_to_tid.keys(), unit=unit
    )
    await db.commit()
    return {"synced": count, "timeframe": TF_FROM_UNIT[unit]}
