from __future__ import annotations

from typing import Annotated, Final, List, Optional, Dict, Any, Iterable, Tuple
from datetime import datetime, timedelta
import re
from fastapi import Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.timezone import kst_ymd_to_utc_naive, kst_ymd_hms_to_utc_naive
from app.repositories.price import upsert_price_data
from app.database import get_session
from app.utils.router import get_router
from app.services.ticker import TickerService
from app.services.kis_prices import KISPrices
from app.services.price import (
    ingest_daily_range,
    Period,         # Literal["D","W","M","Y"]
)

# ---- 동작 기본값(필요하면 여기만 바꾸면 됨) ----
DEFAULT_DAILY_START_YMD: Final[str] = "19900101"         # 일봉 기본 시작일
INTRADAY_LOOKBACK_DAYS: Final[int] = 15                  # 과거 분봉 조회 일수 (영업일 계산 X, 주말 제외만)
RESAMPLE_MINUTES: Final[List[int]] = [5, 15, 30, 60]     # 1분봉 → 리샘플 생성할 분 단위
INCLUDE_TODAY: Final[bool] = True                        # 당일 분봉 포함 여부

DATE_RE = re.compile(r"^\d{8}$")

router = get_router("price")

def _today_ymd_kst() -> str:
    return datetime.now().strftime("%Y%m%d")

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
        raise HTTPException(status_code=400, detail=f"{name}는 YYYYMMDD 형식이어야 합니다.")

async def _upsert_rows(db: AsyncSession, rows: Iterable[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    return await upsert_price_data(db, rows)

# ---------- 리샘플링 유틸 ----------

def _bucket_key_end(hhmmss: str, mins: int) -> str:
    """해당 분이 포함된 버킷의 '끝' 시각으로 스냅 (예: 10:03,5분→10:05:00)."""
    h = int(hhmmss[0:2]); m = int(hhmmss[2:4])
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
            buckets[k] = {"date": r.get("date"), "time": k, "open": o, "high": h, "low": l, "close": c, "volume": vol}
        else:
            # high/low 갱신, close 갱신, volume 누적
            if h is not None: b["high"] = max(b["high"], h)
            if l is not None: b["low"]  = min(b["low"],  l)
            if c is not None: b["close"] = c
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
    summary="단일 종목 전체 동기화 (일봉 전구간 + 최근 N일 분봉 + 당일 분봉)",
    description="""
    식별자(kis_code 또는 symbol)를 통해 단일 종목을 전체 동기화합니다.
    (분봉은 1분 전량 수집 후 5/15/30/60m를 내부 리샘플링합니다)
    """
)
async def ingest_one_stock_all(
    kis_code: Optional[str] = Query(None, description="6자리 KIS 코드 (예: 005930)"),
    symbol:   Optional[str] = Query(None, description="내부 심볼 (예: 005930.KS)"),
    db: Annotated[AsyncSession, Depends(get_session)] = None,
):
    # 0) 입력 검증 ------------------------------------------------------------
    if not kis_code and not symbol:
        raise HTTPException(status_code=400, detail="kis_code 또는 symbol 중 하나는 필수입니다.")

    # 1) 종목 식별 ------------------------------------------------------------
    tsvc = TickerService()
    try:
        ticker_id, code = await tsvc.resolve_one(db, kis_code=kis_code, symbol=symbol)
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    kis = KISPrices()

    # 요약 카운터
    total = 0
    per_tf: Dict[str, int] = {}
    steps: List[str] = []

    try:
        # 2) 일봉 전구간 ------------------------------------------------------
        daily_start = DEFAULT_DAILY_START_YMD
        daily_end   = _today_ymd_kst()
        period: Period = "D"

        daily_items = await kis.get_period_candles(code, daily_start, daily_end, period=period)  # type: ignore[arg-type]
        daily_rows = _rows_from_items(ticker_id, daily_items, "1D")
        synced = await _upsert_rows(db, daily_rows)
        per_tf["1D"] = per_tf.get("1D", 0) + synced
        total += synced
        steps.append(f"D(1D): {synced}")

        # 3) 과거 분봉 (최근 N일) --------------------------------------------
        today_ymd = daily_end
        intraday_dates = _daterange_ymd_for_intraday(today_ymd, INTRADAY_LOOKBACK_DAYS)

        for d in intraday_dates:
            # 1분 전량 수집
            items_1m = await kis.get_intraday_by_date(code, d)
            rows_1m = _rows_from_items(ticker_id, items_1m, "1m")
            s1 = await _upsert_rows(db, rows_1m)
            per_tf["1m"] = per_tf.get("1m", 0) + s1
            total += s1
            steps.append(f"Past {d} (1m/1m): {s1}")

            # 리샘플 TF들
            for mins in RESAMPLE_MINUTES:
                tf = f"{mins}m" if mins < 60 else "1h"
                derived = _resample_from_1m(items_1m, mins)
                rows_tf = _rows_from_items(ticker_id, derived, tf)
                s = await _upsert_rows(db, rows_tf)
                per_tf[tf] = per_tf.get(tf, 0) + s
                total += s
                steps.append(f"Past {d} ({mins}m/{tf}): {s}")

        # 4) 당일 분봉 --------------------------------------------------------
        if INCLUDE_TODAY:
            items_1m = await kis.get_intraday_today(code)
            rows_1m = _rows_from_items(ticker_id, items_1m, "1m")
            s1 = await _upsert_rows(db, rows_1m)
            per_tf["1m"] = per_tf.get("1m", 0) + s1
            total += s1
            steps.append(f"Today (1m/1m): {s1}")

            for mins in RESAMPLE_MINUTES:
                tf = f"{mins}m" if mins < 60 else "1h"
                derived = _resample_from_1m(items_1m, mins)
                rows_tf = _rows_from_items(ticker_id, derived, tf)
                s = await _upsert_rows(db, rows_tf)
                per_tf[tf] = per_tf.get(tf, 0) + s
                total += s
                steps.append(f"Today ({mins}m/{tf}): {s}")

        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"동기화 실패: {e}")

    return {
        "ticker_id": ticker_id,
        "kis_code": code,
        "synced_total": total,
        "synced_by_timeframe": per_tf,
        "steps": steps,
        "notes": (
            f"일봉 {DEFAULT_DAILY_START_YMD}~{_today_ymd_kst()}, "
            f"분봉 최근 {INTRADAY_LOOKBACK_DAYS}일(+당일={INCLUDE_TODAY}), "
            f"리샘플링={RESAMPLE_MINUTES}. (KIS 1분 전량 → 내부 리샘플)"
        ),
    }
