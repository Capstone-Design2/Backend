import asyncio
from datetime import timedelta
from typing import (Any, Dict, Final, Iterable, List, Literal, Mapping, cast)

import pandas as pd
from app.services.ticker import TickerService
import yfinance
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.price import PriceRepository, upsert_price_data
from app.repositories.ticker import TickerRepository
from app.schemas.price import YfinanceRequest
from app.services.kis_prices import KISPrices
from app.utils.timezone import daterange_kst, fmt_ymd, kst_ymd_hms_to_utc_naive, kst_ymd_to_utc_naive, months_ago_kst, today_kst_datetime
from app.utils.resample import resample_from_1m, rows_from_items

# ---- 타입 별칭 ----
Period = Literal["D", "W", "M", "Y"]
Unit = int
TF = Literal["1m", "5m", "15m", "30m", "1h"]

ALLOWED_UNITS: Final[set[int]] = {1, 5, 15, 30, 60}
RESAMPLE_MINUTES: Final[List[int]] = [5, 15, 30, 60]

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
        self.kis_client = KISPrices()
        self.ticker_client = TickerService()
    
    async def sync_daily_prices(
        self,
        db: AsyncSession,
        start_date: str, 
        end_date: str, *, 
        period: Period = "D"
    ) -> dict:
        kis_to_tid = await self.ticker_client.load_kis_to_ticker_id(db)
        count = await ingest_daily_range(
            db, self.kis_client, self.price_repository, kis_to_tid, kis_to_tid.keys(), start_date, end_date, period=period
        )
        
        await db.commit()
        return {"synced": count, "timeframe": "1D"}
    
    async def sync_intraday_by_date(
        self,
        db: AsyncSession,
        date: str,
    ) -> dict:
        kis_to_tid = await self.ticker_client.load_kis_to_ticker_id(db)
        total_synced = 0
        per_tf: Dict[str, int] = {}
        steps: List[str] = []

        for code, ticker_id in kis_to_tid.items():
            # 1분 전량 수집
            items_1m = await self.kis_client.get_intraday_by_date(code, date=date)
            rows_1m = rows_from_items(ticker_id, items_1m, "1m")
            s1 = await _upsert_rows(db, rows_1m)
            total_synced += s1
            per_tf["1m"] = per_tf.get("1m", 0) + s1
            steps.append(f"Past {date} (1m/1m): {s1}")

            # 리샘플링들
            for mins in RESAMPLE_MINUTES:
                tf = f"{mins}m" if mins < 60 else "1h"
                derived = resample_from_1m(items_1m, mins)
                rows_tf = rows_from_items(ticker_id, derived, tf)
                s = await _upsert_rows(db, rows_tf)
                total_synced += s
                per_tf[tf] = per_tf.get(tf, 0) + s
                steps.append(f"Past {date} ({mins}m/{tf}): {s}")

        await db.commit()
        return {"synced": total_synced, "synced_by_timeframe": per_tf, "steps": steps}

    async def sync_intraday_today(
        self,
        db: AsyncSession,
    ) -> dict:
        kis_to_tid = await self.ticker_client.load_kis_to_ticker_id(db)

        total_synced = 0
        per_tf: Dict[str, int] = {}
        steps: List[str] = []
    
        for code, ticker_id in kis_to_tid.items():
            items_1m = await self.kis_client.get_intraday_today(code)
            rows_1m = rows_from_items(ticker_id, items_1m, "1m")
            s1 = await _upsert_rows(db, rows_1m)
            total_synced += s1
            per_tf["1m"] = per_tf.get("1m", 0) + s1
            steps.append(f"Today (1m/1m): {s1}")

            for mins in RESAMPLE_MINUTES:
                tf = f"{mins}m" if mins < 60 else "1h"
                derived = resample_from_1m(items_1m, mins)
                rows_tf = rows_from_items(ticker_id, derived, tf)
                s = await _upsert_rows(db, rows_tf)
                total_synced += s
                per_tf[tf] = per_tf.get(tf, 0) + s
                steps.append(f"Today ({mins}m/{tf}): {s}")

        await db.commit()
        return {"synced": total_synced, "synced_by_timeframe": per_tf, "steps": steps}
    
    async def ingest_one_stock_all(
        self,
        db: AsyncSession,
        years: int,
        months: int,
        period: Period = "D",
    ) -> dict:
        
        try:
            # 삼성전자 코드
            ticker_id, code = await self.ticker_client.resolve_one(db, kis_code="005930")
        except (ValueError, LookupError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        kis = self.kis_client
        
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
                    fmt_ymd(now_start),
                    fmt_ymd(now_end),
                    period=period
                )

                daily_rows = rows_from_items(ticker_id, daily_items, "1D")
                synced = await _upsert_rows(db, daily_rows)
                await db.commit()

                per_tf["1D"] = per_tf.get("1D", 0) + synced
                total += synced
                steps.append(
                    f"D(1D) {fmt_ymd(now_start)}~{fmt_ymd(now_end)}: {synced}")

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

                rows_1m = rows_from_items(ticker_id, items_1m, "1m")
                s1 = await _upsert_rows(db, rows_1m)
                per_tf["1m"] = per_tf.get("1m", 0) + s1
                total += s1
                steps.append(f"1m {ymd}: {s1}")

                # 파생 리샘플 TF
                if items_1m:
                    for mins in RESAMPLE_MINUTES:
                        tf = f"{mins}m" if mins < 60 else "1h"
                        derived = resample_from_1m(items_1m, mins)
                        rows_tf = rows_from_items(ticker_id, derived, tf)
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
    
    async def _upsert_rows(db: AsyncSession, rows: Iterable[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        return await upsert_price_data(db, rows)
