import asyncio
from typing import (Any, Dict, Final, Iterable, List, Literal, Mapping, Union,
                    cast)

import pandas as pd
import yfinance
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticker import Ticker
from app.repositories.price import PriceRepository, upsert_price_data
from app.repositories.ticker import TickerRepository
from app.schemas.price import YfinanceRequest
from app.services.kis_prices import KISPrices
from app.utils.timezone import kst_ymd_hms_to_utc_naive, kst_ymd_to_utc_naive

# ---- 타입 별칭 ----
Period = Literal["D", "W", "M", "Y"]
Unit = int
TF = Literal["1m", "5m", "15m", "30m", "1h"]

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
        ts_utc = kst_ymd_hms_to_utc_naive(
            it["date"], it["time"])  # KST -> UTC naive
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


class PriceService:
    def __init__(self):
        self.price_repository = PriceRepository()
        self.ticker_repository = TickerRepository()

    async def update_price_from_yfinance(
        self,
        request: YfinanceRequest,
        db: AsyncSession
    ) -> str:
        try:
            # 1. Ticker 조회
            ticker = await self.ticker_repository.get_by_name(request.ticker_name, db)
            if not ticker:
                raise HTTPException(status_code=404, detail="Ticker not found")

            # 2. yfinance 동기 함수를 별도 스레드에서 실행
            symbol = ticker.symbol
            df = await asyncio.to_thread(
                yfinance.download,
                symbol,
                period=request.period,
                interval=request.interval,
                progress=False,
                auto_adjust=False,  # ✅ 조정 안 함 → 정수로 나옴
            )

            if df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data found for {symbol}"
                )

            # ✅ 멀티인덱스 컬럼을 평평하게 만들기
            if isinstance(df.columns, pd.MultiIndex):
                # 컬럼이 ('Close', '005930.KS') 형태면 'Close'만 추출
                df.columns = df.columns.get_level_values(0)

            # 3. DataFrame → DB 레코드 변환
            rows = self._parsing_yfinance_data(
                ticker.ticker_id, request.interval, df)

            # 4. DB 저장
            update_len = await upsert_price_data(db, rows)
            await db.commit()

            return f"Successfully updated {request.ticker_name} from yfinance, updated {update_len} rows"

        except Exception as e:
            await db.rollback()
            # 더 자세한 에러 정보 출력
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update price from yfinance: {str(e)} (Type: {type(e).__name__})"
            )

    def _parsing_yfinance_data(self,
                               ticker_id: int,
                               interval: str,
                               df
                               ) -> List[Dict[str, Any]]:

        rows = []

        # to_dict()로 변환하여 안전하게 처리
        records = df.to_dict('index')

        # yfinance interval('1d') → DB timeframe('1D') 변환
        timeframe = interval.upper()

        for timestamp, data in records.items():
            # 이제 'Open', 'High' 등으로 직접 접근 가능
            open_val = data.get('Open')
            high_val = data.get('High')
            low_val = data.get('Low')
            close_val = data.get('Close')
            volume_val = data.get('Volume')

            rows.append({
                "ticker_id": int(ticker_id),
                "timestamp": pd.Timestamp(timestamp).to_pydatetime(),
                "timeframe": timeframe,
                "open": None if (open_val is None or pd.isna(open_val)) else float(open_val),
                "high": None if (high_val is None or pd.isna(high_val)) else float(high_val),
                "low": None if (low_val is None or pd.isna(low_val)) else float(low_val),
                "close": None if (close_val is None or pd.isna(close_val)) else float(close_val),
                "volume": None if (volume_val is None or pd.isna(volume_val)) else int(float(volume_val)),
                "source": "yfinance",
                "is_adjusted": False
            })

        return rows
