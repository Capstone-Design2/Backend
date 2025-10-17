from typing import Dict, Iterable, List, Final, Literal, Mapping, cast, Union
from app.services.kis_prices import KISPrices
from app.utils.timezone import kst_ymd_to_utc_naive, kst_ymd_hms_to_utc_naive
from app.repositories.price import upsert_price_data

# ---- 타입 별칭 ----
Period = Literal["D", "W", "M", "Y"]
Unit   = int
TF     = Literal["1m", "5m", "15m", "30m", "1h"]

ALLOWED_UNITS: Final[set[int]] = {1, 5, 15, 30, 60}

# Unit(int) -> Timeframe 매핑
TF_FROM_UNIT: Final[Mapping[int, TF]] = {
    1:  "1m",
    5:  "5m",
    15: "15m",
    30: "30m",
    60: "1h",
}

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
        ts_utc = kst_ymd_to_utc_naive(it["date"])  # YYYYMMDD -> UTC naive
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
        ts_utc = kst_ymd_hms_to_utc_naive(it["date"], it["time"])  # KST -> UTC naive
        out.append({
            "ticker_id": ticker_id, "timestamp": ts_utc, "timeframe": tf,
            "open": it.get("open"), "high": it.get("high"),
            "low": it.get("low"), "close": it.get("close"),
            "volume": it.get("volume"), "source": "KIS", "is_adjusted": False,
        })
    return out

async def ingest_daily_range(
    db,
    kis: KISPrices,
    kis_to_tid: Dict[str, int],
    kis_codes: Iterable[str],
    start_date: str,
    end_date: str,
    period: Period = "D",     # <- Literal로 좁힘
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
            total += await upsert_price_data(db, buf)
            buf.clear()
    if buf:
        total += await upsert_price_data(db, buf)
    return total

async def ingest_intraday_by_date(
    db,
    kis: KISPrices,
    kis_to_tid: Dict[str, int],
    kis_codes: Iterable[str],
    date: str,
    unit: Unit = 1,           # <- Literal로 좁힘
    batch: int = 2000,
) -> int:
    total = 0
    buf: List[dict] = []
    unit = _ensure_unit(unit)

    for code in kis_codes:
        tid = kis_to_tid.get(code)
        if not tid:
            continue
        items = await kis.get_intraday_by_date(code, date, unit=unit)
        buf.extend(_to_records_intraday(tid, items, unit))
        if len(buf) >= batch:
            total += await upsert_price_data(db, buf)
            buf.clear()
    if buf:
        total += await upsert_price_data(db, buf)
    return total

async def ingest_intraday_today(
    db,
    kis: KISPrices,
    kis_to_tid: Dict[str, int],
    kis_codes: Iterable[str],
    unit: Unit = 1,           # <- Literal로 좁힘
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
            total += await upsert_price_data(db, buf)
            buf.clear()
    if buf:
        total += await upsert_price_data(db, buf)
    return total
