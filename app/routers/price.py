# app/api/price_router.py
from __future__ import annotations
from app.services.price import Period
from fastapi import Depends, Query, HTTPException
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.di import get_price_service
from app.services.price_service import PriceService
from app.utils.router import get_router

router = get_router("price")

@router.post("/daily", summary="국내주식 일별 시세 동기화 (KIS)")
async def sync_daily_prices(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    start_date: Annotated[str, Query(description="YYYYMMDD")] = ...,
    end_date:   Annotated[str, Query(description="YYYYMMDD")] = ...,
):
    try:
        return await price_svc.sync_daily_prices(db, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/intraday/by-date", summary="국내주식 과거 분봉 시세 동기화 (KIS)")
async def sync_intraday_by_date(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    date: Annotated[str, Query(description="YYYYMMDD")] = ...,
):
    try:
        return await price_svc.sync_intraday_by_date(db, date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/intraday/today", summary="국내주식 당일 분봉 시세 동기화 (KIS)")
async def sync_intraday_today(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
):
    return await price_svc.sync_intraday_today(db)

@router.post("/one/all", summary="삼성전자 일봉(3년)+분봉(1개월) 데이터 동기화 (KIS)")
async def ingest_one_stock_all(
    db: Annotated[AsyncSession, Depends(get_session)],
    price_svc: Annotated[PriceService, Depends(get_price_service)],
    years: int = 3,
    months: int = 1,
    period: Period = "D",
):
    return await price_svc.ingest_one_stock_all(db, years=years, months=months, period=period)
