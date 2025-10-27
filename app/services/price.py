from typing import Dict, Iterable, List, Final, Literal, Mapping, cast
from sqlalchemy.ext.asyncio import AsyncSession

# 프로토콜에만 의존
from app.services.protocols import KISClient, PriceRepository, TickerClient
from app.utils.timezone import (
    kst_ymd_to_utc_naive,
    kst_ymd_hms_to_utc_naive,
    today_kst_datetime,
    months_ago_kst,
    fmt_ymd,
)

# ---- 타입 별칭 ----
Period = Literal["D", "W", "M", "Y"]
Unit   = int
TF     = Literal["1m", "5m", "15m", "30m", "1h"]

ALLOWED_UNITS: Final[set[int]] = {1, 5, 15, 30, 60}

TF_FROM_UNIT: Final[Mapping[int, TF]] = {1:"1m", 5:"5m", 15:"15m", 30:"30m", 60:"1h"}

# 리샘플 분 목록(필요 시 오버라이드)
RESAMPLE_MINUTES_DEFAULT: Final[tuple[int, ...]] = (5, 15, 30, 60)

# ---- 런타임 검증 유틸 ----
def _ensure_period(p: str) -> Period:
    if p not in ("D", "W", "M", "Y"):
        raise ValueError(f"period must be one of 'D','W','M','Y', got {p!r}")
    return cast(Period, p)

def _ensure_unit(u: int) -> Unit:
    if u not in ALLOWED_UNITS:
        raise ValueError(f"unit must be one of 1,5,15,30,60, got {u!r}")
    return u

def _to_records_daily(ticker_id: int, items: List[dict]) -> List[dict]:
    out: List[dict] = []
    for it in items:
        ts_utc = kst_ymd_to_utc_naive(it["date"])
        out.append({
            "ticker_id": ticker_id, "timestamp": ts_utc, "timeframe": "1D",
            "open": it.get("open"), "high": it.get("high"),
            "low": it.get("low"), "close": it.get("close"),
            "volume": it.get("volume"), "source": "KIS", "is_adjusted": False,
        })
    return out

def _to_records_intraday(ticker_id: int, items: List[dict], unit: Unit) -> List[dict]:
    tf: TF = TF_FROM_UNIT[unit]
    out: List[dict] = []
    for it in items:
        ts_utc = kst_ymd_hms_to_utc_naive(it["date"], it["time"])
        out.append({
            "ticker_id": ticker_id, "timestamp": ts_utc, "timeframe": tf,
            "open": it.get("open"), "high": it.get("high"),
            "low": it.get("low"), "close": it.get("close"),
            "volume": it.get("volume"), "source": "KIS", "is_adjusted": False,
        })
    return out

# ---- 1분 → N분 리샘플 유틸 ----
def _bucket_key_end(hhmmss: str, mins: int) -> str:
    h = int(hhmmss[0:2]); m = int(hhmmss[2:4])
    end_min = ((m // mins) + 1) * mins
    if end_min >= 60:
        h = (h + 1) % 24
        end_min -= 60
    return f"{h:02d}{end_min:02d}00"

def _resample_from_1m(items_1m: List[dict], mins: int) -> List[dict]:
    buckets: Dict[str, dict] = {}
    for r in items_1m:
        t = str(r.get("time", ""))
        if len(t) != 6 or not t.isdigit():
            continue
        k = _bucket_key_end(t, mins)
        o, h, l, c = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        v = int(r.get("volume") or 0)
        b = buckets.get(k)
        if b is None:
            buckets[k] = {"date": r.get("date"), "time": k, "open": o, "high": h, "low": l, "close": c, "volume": v}
        else:
            if h is not None: b["high"] = max(b["high"], h)
            if l is not None: b["low"]  = min(b["low"],  l)
            if c is not None: b["close"] = c
            b["volume"] += v
    return list(buckets.values())

# ----------------- 유스케이스 함수들 -----------------

async def ingest_daily_range(
    db: AsyncSession,
    kis: KISClient,
    repo: PriceRepository,
    kis_to_tid: Dict[str, int],
    kis_codes: Iterable[str],
    start_date: str,
    end_date: str,
    period: Period = "D",
    batch: int = 2000,
) -> int:
    total = 0
    buf: List[dict] = []
    period = _ensure_period(period)

    for code in kis_codes:
        tid = kis_to_tid.get(code)
        if not tid:
            continue
        items = await kis.get_period_candles(code, start_date, end_date, period=period)
        buf.extend(_to_records_daily(tid, items))
        if len(buf) >= batch:
            total += await repo.upsert_price_data(db, buf)
            buf.clear()

    if buf:
        total += await repo.upsert_price_data(db, buf)
    return total

async def ingest_intraday_by_date(
    db: AsyncSession,
    kis: KISClient,
    repo: PriceRepository,
    kis_to_tid: Dict[str, int],
    kis_codes: Iterable[str],
    date: str,
    unit: Unit = 1,
    batch: int = 2000,
) -> int:
    total = 0
    buf: List[dict] = []
    unit = _ensure_unit(unit)

    for code in kis_codes:
        tid = kis_to_tid.get(code)
        if not tid:
            continue
        items = await kis.get_intraday_by_date(code, date=date, unit=unit)
        buf.extend(_to_records_intraday(tid, items, unit))
        if len(buf) >= batch:
            total += await repo.upsert_price_data(db, buf)
            buf.clear()

    if buf:
        total += await repo.upsert_price_data(db, buf)
    return total

async def ingest_intraday_today(
    db: AsyncSession,
    kis: KISClient,
    repo: PriceRepository,
    kis_to_tid: Dict[str, int],
    kis_codes: Iterable[str],
    unit: Unit = 1,
    batch: int = 2000,
) -> int:
    total = 0
    buf: List[dict] = []
    unit = _ensure_unit(unit)

    for code in kis_codes:
        tid = kis_to_tid.get(code)
        if not tid:
            continue
        items = await kis.get_intraday_today(code, unit=unit)
        buf.extend(_to_records_intraday(tid, items, unit))
        if len(buf) >= batch:
            total += await repo.upsert_price_data(db, buf)
            buf.clear()

    if buf:
        total += await repo.upsert_price_data(db, buf)
    return total

# ----------------- 삼성전자(005930) 전용: 일봉(3y)+분봉(N개월) -----------------

async def ingest_one_stock_all(
    db: AsyncSession,
    kis: KISClient,
    repo: PriceRepository,
    ticker: TickerClient,
    *,
    years: int = 3,
    months: int = 1,
    period: Period = "D",
    resample_minutes: Iterable[int] = RESAMPLE_MINUTES_DEFAULT,
    daily_chunk_days: int = 99,
    sleep_daily_sec: float = 0.2,
    sleep_intraday_sec: float = 0.15,
) -> dict:
    """
    삼성전자(005930) 일봉(최근 years년) + 분봉(최근 months개월: 1m + 리샘플 5/15/30/60m) 수집 후 upsert.
    라우터가 아닌 유스케이스 함수이므로 HTTP 상태 대신 ValueError/RuntimeError를 발생시킵니다.
    """
    # 1) 종목 식별
    try:
        ticker_id, code = await ticker.resolve_one(db, kis_code="005930")
    except (ValueError, LookupError) as e:
        raise ValueError(str(e))

    total = 0
    per_tf: Dict[str, int] = {}
    steps: List[str] = []

    # 2) 일봉: 99일 단위로 분할 호출
    daily_end = today_kst_datetime()
    daily_start = daily_end - timedelta(days=365 * years)
    now_end = daily_end

    while now_end >= daily_start:
        now_start = max(daily_start, now_end - timedelta(days=daily_chunk_days))
        items = await kis.get_period_candles(code, fmt_ymd(now_start), fmt_ymd(now_end), period=period)
        rows = _to_records_daily(ticker_id, items)
        synced = 0
        if rows:
            synced = await repo.upsert_price_data(db, rows)
        await db.commit()

        per_tf["1D"] = per_tf.get("1D", 0) + synced
        total += synced
        steps.append(f"D(1D) {fmt_ymd(now_start)}~{fmt_ymd(now_end)}: {synced}")

        now_end = now_start - timedelta(days=1)
        if sleep_daily_sec:
            import asyncio
            await asyncio.sleep(sleep_daily_sec)

    # 3) 분봉: 최근 months개월(1m + 리샘플)
    try:
        intraday_end = today_kst_datetime()
        intraday_start = months_ago_kst(intraday_end, months)

        d = intraday_start
        from datetime import timedelta as _td
        while d <= intraday_end - _td(days=1):
            ymd = d.strftime("%Y%m%d")
            items_1m = await kis.get_intraday_by_date(code, date=ymd, unit=1)  # 1분봉만 요청

            # 1m 업서트
            rows_1m = _to_records_intraday(ticker_id, items_1m, 1)
            s1 = 0
            if rows_1m:
                s1 = await repo.upsert_price_data(db, rows_1m)
            per_tf["1m"] = per_tf.get("1m", 0) + s1
            total += s1
            steps.append(f"1m {ymd}: {s1}")

            # 리샘플 업서트
            if items_1m:
                for mins in resample_minutes:
                    tf_unit: Unit = mins if mins < 60 else 60
                    derived = _resample_from_1m(items_1m, mins)
                    rows_tf = _to_records_intraday(ticker_id, derived, tf_unit)
                    s = 0
                    if rows_tf:
                        s = await repo.upsert_price_data(db, rows_tf)
                    key = TF_FROM_UNIT[tf_unit]
                    per_tf[key] = per_tf.get(key, 0) + s
                    total += s
                    steps.append(f"{key} {ymd}: {s}")

            await db.commit()
            if sleep_intraday_sec:
                import asyncio
                await asyncio.sleep(sleep_intraday_sec)

            d += _td(days=1)

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"분봉 동기화 실패: {e}")

    return {
        "ticker_id": ticker_id,
        "kis_code": code,
        "synced_total": total,
        "synced_by_timeframe": per_tf,
        "steps": steps,
        "notes": f"일봉={years}년, 분봉={months}개월(1m 전량 수집 후 리샘플 5/15/30/60m)."
    }

# 필요한 표준 라이브러리 import (위에서 사용)
from datetime import timedelta
