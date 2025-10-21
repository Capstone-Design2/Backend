from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, Final, Iterable, List, Optional, Tuple

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.repositories.price import upsert_price_data
from app.schemas.price import YfinanceRequest
from app.services.kis_prices import KISPrices
from app.services.price import Period  # Literal["D","W","M","Y"]
from app.services.price import PriceService, ingest_daily_range
from app.services.ticker import TickerService
from app.utils.dependencies import get_price_service
from app.utils.router import get_router
from app.utils.timezone import (_fmt_ymd, daterange_kst,
                                kst_ymd_hms_to_utc_naive, kst_ymd_to_utc_naive,
                                months_ago_kst, today_kst_datetime)

# ---- 동작 기본값(필요하면 여기만 바꾸면 됨) ----
# 과거 분봉 조회 일수 (영업일 계산 X, 주말 제외만)
INTRADAY_LOOKBACK_DAYS: Final[int] = 30
RESAMPLE_MINUTES: Final[List[int]] = [5, 15, 30, 60]     # 1분봉 → 리샘플 생성할 분 단위
INCLUDE_TODAY: Final[bool] = True                        # 당일 분봉 포함 여부

DATE_RE = re.compile(r"^\d{8}$")

router = get_router("price")


def _daterange_ymd_for_intraday(end_ymd: str, days: int) -> List[str]:
    """주말(토/일)만 제외하고 최근 days일의 YYYYMMDD 목록 생성 (end_ymd 포함 X)"""
    end_dt = datetime.strptime(end_ymd, "%Y%m%d")
    out: List[str] = []
    d = end_dt - timedelta(days=1)
    while len(out) < days:
        if d.weekday() < 5:  # 0=월 ... 4=금
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    out.reverse()
    return out


def _assert_yyyymmdd(name: str, value: str) -> None:
    if not DATE_RE.match(value or ""):
        raise HTTPException(
            status_code=400, detail=f"{name}는 YYYYMMDD 형식이어야 합니다.")


async def _upsert_rows(db: AsyncSession, rows: Iterable[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    return await upsert_price_data(db, rows)

# ---------- 리샘플링 유틸 ----------


def _bucket_key_end(hhmmss: str, mins: int) -> str:
    """해당 분이 포함된 버킷의 '끝' 시각으로 스냅 (예: 10:03,5분→10:05:00)."""
    h = int(hhmmss[0:2])
    m = int(hhmmss[2:4])
    end_min = ((m // mins) + 1) * mins
    if end_min >= 60:
        h = (h + 1) % 24
        end_min -= 60
    return f"{h:02d}{end_min:02d}00"


def _resample_from_1m(items_1m: List[Dict[str, Any]], mins: int) -> List[Dict[str, Any]]:
    """1분봉 리스트 → N분봉 리스트(open=첫, high=max, low=min, close=마지막, volume=sum)."""
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in items_1m:
        t = r.get("time")
        if not t or len(t) != 6 or not str(t).isdigit():
            continue
        k = _bucket_key_end(str(t), mins)
        o, h, l, c = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        v = r.get("volume")
        vol = int(v) if v is not None else 0
        b = buckets.get(k)
        if b is None:
            buckets[k] = {"date": r.get(
                "date"), "time": k, "open": o, "high": h, "low": l, "close": c, "volume": vol}
        else:
            # high/low 갱신, close 갱신, volume 누적
            if h is not None:
                b["high"] = max(b["high"], h)
            if l is not None:
                b["low"] = min(b["low"],  l)
            if c is not None:
                b["close"] = c
            b["volume"] += vol
    return list(buckets.values())


def _rows_from_items(
    ticker_id: int,
    items: List[Dict[str, Any]],
    timeframe: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if timeframe == "1D":
        for it in items:
            rows.append({
                "ticker_id": ticker_id,
                "timestamp": kst_ymd_to_utc_naive(it["date"]),
                "timeframe": "1D",
                "open": it.get("open"),
                "high": it.get("high"),
                "low": it.get("low"),
                "close": it.get("close"),
                "volume": it.get("volume"),
                "source": "KIS",
                "is_adjusted": False,
            })
    else:
        for it in items:
            rows.append({
                "ticker_id": ticker_id,
                "timestamp": kst_ymd_hms_to_utc_naive(str(it["date"]), str(it["time"])),
                "timeframe": timeframe,
                "open": it.get("open"),
                "high": it.get("high"),
                "low": it.get("low"),
                "close": it.get("close"),
                "volume": it.get("volume"),
                "source": "KIS",
                "is_adjusted": False,
            })
    return rows

# ---------- 엔드포인트 ----------


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
    _assert_yyyymmdd("start_date", start_date)
    _assert_yyyymmdd("end_date", end_date)

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
    지정된 날짜(YYYYMMDD)의 과거 1분봉을 전량 수집(30건 페이징)하고,
    1m + (5/15/30/60m 리샘플링)을 price_data에 upsert합니다.
    """,
)
async def sync_intraday_by_date(
    db: Annotated[AsyncSession, Depends(get_session)],
    date: Annotated[str, Query(description="YYYYMMDD")] = ...,
):
    _assert_yyyymmdd("date", date)

    tsvc = TickerService()
    kis_to_tid = await tsvc.load_kis_to_ticker_id(db)
    kis = KISPrices()

    total_synced = 0
    per_tf: Dict[str, int] = {}
    steps: List[str] = []

    for code, ticker_id in kis_to_tid.items():
        # 1분 전량 수집
        items_1m = await kis.get_intraday_by_date(code, date=date)
        rows_1m = _rows_from_items(ticker_id, items_1m, "1m")
        s1 = await _upsert_rows(db, rows_1m)
        total_synced += s1
        per_tf["1m"] = per_tf.get("1m", 0) + s1
        steps.append(f"Past {date} (1m/1m): {s1}")

        # 리샘플링들
        for mins in RESAMPLE_MINUTES:
            tf = f"{mins}m" if mins < 60 else "1h"
            derived = _resample_from_1m(items_1m, mins)
            rows_tf = _rows_from_items(ticker_id, derived, tf)
            s = await _upsert_rows(db, rows_tf)
            total_synced += s
            per_tf[tf] = per_tf.get(tf, 0) + s
            steps.append(f"Past {date} ({mins}m/{tf}): {s}")

    await db.commit()
    return {"synced": total_synced, "synced_by_timeframe": per_tf, "steps": steps}


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
):
    tsvc = TickerService()
    kis_to_tid = await tsvc.load_kis_to_ticker_id(db)
    kis = KISPrices()

    total_synced = 0
    per_tf: Dict[str, int] = {}
    steps: List[str] = []

    for code, ticker_id in kis_to_tid.items():
        items_1m = await kis.get_intraday_today(code)
        rows_1m = _rows_from_items(ticker_id, items_1m, "1m")
        s1 = await _upsert_rows(db, rows_1m)
        total_synced += s1
        per_tf["1m"] = per_tf.get("1m", 0) + s1
        steps.append(f"Today (1m/1m): {s1}")

        for mins in RESAMPLE_MINUTES:
            tf = f"{mins}m" if mins < 60 else "1h"
            derived = _resample_from_1m(items_1m, mins)
            rows_tf = _rows_from_items(ticker_id, derived, tf)
            s = await _upsert_rows(db, rows_tf)
            total_synced += s
            per_tf[tf] = per_tf.get(tf, 0) + s
            steps.append(f"Today ({mins}m/{tf}): {s}")

    await db.commit()
    return {"synced": total_synced, "synced_by_timeframe": per_tf, "steps": steps}


@router.post(
    "/one/all",
    summary="삼성전자 일봉(3년)+분봉(1개월) 데이터 동기화 (KIS)",
    description="""
    삼성전자 일봉(3년)+분봉(1개월) 데이터를 수집하고 price_data 테이블에 upsert합니다.
    """
)
async def ingest_one_stock_all(
    db: Annotated[AsyncSession, Depends(get_session)] = None,
    years: int = 3,
    months: int = 1,
    period: Period = "D"
):

    # 1) 종목 식별 ------------------------------------------------------------
    tsvc = TickerService()
    try:
        # 삼성전자 코드
        ticker_id, code = await tsvc.resolve_one(db, kis_code="005930")
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    kis = KISPrices()

    # 요약 카운터
    total = 0
    per_tf: Dict[str, int] = {}
    steps: List[str] = []

    # 목표 기간 계산
    daily_end = today_kst_datetime()
    daily_start = daily_end - timedelta(days=365 * years)

    now_end = daily_end
    while now_end >= daily_start:
        now_start = max(daily_start, now_end - timedelta(days=99))

        try:
            # 2) 일봉 전구간 ------------------------------------------------------
            daily_items = await kis.get_period_candles(
                code,
                _fmt_ymd(now_start),
                _fmt_ymd(now_end),
                period=period
            )

            daily_rows = _rows_from_items(ticker_id, daily_items, "1D")
            synced = await _upsert_rows(db, daily_rows)
            await db.commit()

            per_tf["1D"] = per_tf.get("1D", 0) + synced
            total += synced
            steps.append(
                f"D(1D) {_fmt_ymd(now_start)}~{_fmt_ymd(now_end)}: {synced}")

            now_end = now_start - timedelta(days=1)
            await asyncio.sleep(0.2)

        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"동기화 실패: {e}")

        # 3) 과거 분봉 (최근 N개월) --------------------------------------------
    try:
        intraday_end = today_kst_datetime()
        intraday_start = months_ago_kst(intraday_end, months)

        for d in daterange_kst(intraday_start, intraday_end - timedelta(days=1)):
            ymd = d.strftime("%Y%m%d")
            items_1m = await kis.get_intraday_by_date(code, date=ymd)

            rows_1m = _rows_from_items(ticker_id, items_1m, "1m")
            s1 = await _upsert_rows(db, rows_1m)
            per_tf["1m"] = per_tf.get("1m", 0) + s1
            total += s1
            steps.append(f"1m {ymd}: {s1}")

            # 파생 리샘플 TF
            if items_1m:
                for mins in RESAMPLE_MINUTES:
                    tf = f"{mins}m" if mins < 60 else "1h"
                    derived = _resample_from_1m(items_1m, mins)
                    rows_tf = _rows_from_items(ticker_id, derived, tf)
                    s = await _upsert_rows(db, rows_tf)
                    per_tf[tf] = per_tf.get(tf, 0) + s
                    total += s
                    steps.append(f"{tf} {ymd}: {s}")

            await db.commit()
            await asyncio.sleep(0.15)  # 레이트 리밋 여유
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"분봉 동기화 실패: {e}")

    return {
        "ticker_id": ticker_id,
        "kis_code": code,
        "synced_total": total,
        "synced_by_timeframe": per_tf,
        "steps": steps,
        "notes": f"일봉={years}년, 분봉={months}개월(1m 전량 수집 후 리샘플 5/15/30/60m)."
    }


@router.post("/yfinance")
async def update_price_from_yfinance(
    request: YfinanceRequest,
    service: Annotated[PriceService, Depends(get_price_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    result = await service.update_price_from_yfinance(request, db)
    return result
