from __future__ import annotations

from typing import Annotated
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.di import get_price_service
from app.services.price_service import PriceService
from app.services.price import Period
from app.utils.router import get_router
from app.schemas.price import YfinanceRequest

router = get_router("price")

@router.post(
    "/daily",
    summary="국내주식 일별 시세 동기화 (KIS)",
    description="지정된 기간 동안의 일봉(OHLCV) 데이터를 수집하고 price_data 테이블에 upsert합니다.",
)
async def sync_daily_prices(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    start_date: Annotated[str, Query(description="YYYYMMDD")] = ...,
    end_date:   Annotated[str, Query(description="YYYYMMDD")] = ...,
    period: Annotated[Period, Query(description="D/W/M/Y")] = "D",
):
    try:
        return await price_svc.sync_daily_prices(db, start_date, end_date, period=period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/intraday/by-date",
    summary="국내주식 과거 분봉 시세 동기화 (KIS)",
    description="지정된 날짜(YYYYMMDD)의 과거 1분봉을 수집합니다(파생 리샘플은 서비스에서 처리).",
)
async def sync_intraday_by_date(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    date: Annotated[str, Query(description="YYYYMMDD")] = ...,
    unit: Annotated[int, Query(description="1,5,15,30,60")] = 1,
):
    try:
        return await price_svc.sync_intraday_by_date(db, date, unit=unit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/intraday/today",
    summary="국내주식 당일 분봉 시세 동기화 (KIS)",
    description="현재 거래일의 1분봉을 수집합니다(파생 리샘플은 서비스에서 처리).",
)
async def sync_intraday_today(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    unit: Annotated[int, Query(description="1,5,15,30,60")] = 1,
):
    return await price_svc.sync_intraday_today(db, unit=unit)

@router.post(
    "/one/all",
    summary="삼성전자 일봉(3년)+분봉(1개월) 데이터 동기화 (KIS)",
    description="삼성전자(005930) 일봉(최근 N년) + 분봉(최근 N개월)을 수집해 저장합니다.",
)
async def ingest_one_stock_all(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    years: int = 3,
    months: int = 1,
    period: Annotated[Period, Query(description="D/W/M/Y")] = "D",
):
    return await price_svc.ingest_one_stock_all(db, years=years, months=months, period=period)

@router.post("/yfinance", summary="야후 파이낸스 기반 가격 업데이트")
async def update_price_from_yfinance(
    request: YfinanceRequest,
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    return await price_svc.update_price_from_yfinance(request, db)
