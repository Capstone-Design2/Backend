from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.price import YfinanceRequest
from app.services.price import Period
from app.services.price import PriceService
from app.utils.dependencies import get_price_service
from app.utils.router import get_router
from app.utils.timezone import assert_yyyymmdd

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
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    start_date: Annotated[str, Query(description="YYYYMMDD")] = ...,
    end_date:   Annotated[str, Query(description="YYYYMMDD")] = ...,
    period: Annotated[Period, Query(description="D/W/M/Y")] = "D",
):
    assert_yyyymmdd("start_date", start_date)
    assert_yyyymmdd("end_date", end_date)
    try:
        return await price_svc.sync_daily_prices(db, start_date, end_date, period=period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/intraday/by-date",
    summary="국내주식 과거 분봉 시세 동기화 (KIS)",
    description="""
    지정된 날짜(YYYYMMDD)의 과거 1분봉을 전량 수집(30건 페이징)하고,
    1m + (5/15/30/60m 리샘플링)을 price_data에 upsert합니다.
    """,
)
async def sync_intraday_by_date(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    date: Annotated[str, Query(description="YYYYMMDD")] = ...,
):
    assert_yyyymmdd("date", date)
    try:
        return await price_svc.sync_intraday_by_date(db, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/intraday/today",
    summary="국내주식 당일 분봉 시세 동기화 (KIS)",
    description="""
    현재 거래일의 1분봉을 전량 수집(30건 페이징)하고,
    1m + (5/15/30/60m 리샘플링)을 price_data에 upsert합니다.
    """,
)
async def sync_intraday_today(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
):
    return await price_svc.sync_intraday_today(db)
    

@router.post(
    "/one/all",
    summary="삼성전자 일봉(x년)+분봉(y개월) 데이터 동기화 (KIS)",
    description="""
    삼성전자 일봉(x년)+분봉(y개월) 데이터를 수집하고 price_data 테이블에 upsert합니다.
    """
)
async def ingest_one_stock_all(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    years: int = 3,
    months: int = 1,
):
    return await price_svc.ingest_one_stock_all(db, years=years, months=months)

@router.post("/yfinance")
async def update_price_from_yfinance(
    request: YfinanceRequest,
    service: Annotated[PriceService, Depends(get_price_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    result = await service.update_price_from_yfinance(request, db)
    return result
