"""
실시간 시세 데이터를 price_data 테이블에 저장하는 서비스
PriceEventBus를 구독하여 받은 실시간 가격을 DB에 기록
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.events import get_price_event_bus, PriceEvent
from app.database import get_session
from app.models.price_data import PriceData
from app.repositories.ticker import TickerRepository

logger = logging.getLogger(__name__)


class PriceDataRecorder:
    """
    실시간 시세를 DB에 기록하는 서비스

    - 1분봉 기준으로 OHLCV 데이터 생성
    - 같은 분 내에서는 high/low 업데이트, close 갱신
    - 새로운 분이 시작되면 새 레코드 생성
    """

    def __init__(self):
        self.event_bus = get_price_event_bus()
        self.is_running = False

        # 메모리 캐시: ticker_code -> (ticker_id, current_minute_candle)
        self.candle_cache: Dict[str, Dict] = {}

    def _get_minute_timestamp(self, dt: datetime) -> datetime:
        """
        주어진 시간을 1분 단위로 truncate (초/마이크로초 제거)
        예: 2025-12-01 10:35:42 -> 2025-12-01 10:35:00
        """
        return dt.replace(second=0, microsecond=0)

    async def _get_ticker_id(self, db: AsyncSession, ticker_code: str) -> Optional[int]:
        """KIS 종목 코드로 ticker_id 조회"""
        ticker_repo = TickerRepository()
        ticker = await ticker_repo.get_ticker_by_kis_code(db, ticker_code)

        if not ticker:
            logger.warning(f"종목 코드 {ticker_code}에 해당하는 Ticker를 찾을 수 없습니다.")
            return None

        return ticker.ticker_id

    async def _upsert_price_data(
        self,
        db: AsyncSession,
        ticker_id: int,
        timestamp: datetime,
        price: Decimal,
        volume: int,
    ) -> None:
        """
        price_data 테이블에 1분봉 데이터 upsert

        - 같은 분의 데이터가 있으면 high/low/close/volume 업데이트
        - 없으면 새로 생성 (open=high=low=close=price)
        """
        minute_ts = self._get_minute_timestamp(timestamp)

        # 기존 데이터 조회
        stmt = select(PriceData).where(
            and_(
                PriceData.ticker_id == ticker_id,
                PriceData.timestamp == minute_ts,
                PriceData.timeframe == "1m",
                PriceData.source == "KIS_REALTIME",
            )
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # 기존 캔들 업데이트
            existing.high = max(existing.high, price)
            existing.low = min(existing.low, price)
            existing.close = price
            existing.volume = volume  # 최신 누적 거래량으로 갱신
            existing.updated_at = datetime.now(timezone.utc)

            logger.debug(
                f"1분봉 업데이트: ticker_id={ticker_id}, ts={minute_ts}, "
                f"OHLC={existing.open}/{existing.high}/{existing.low}/{existing.close}"
            )
        else:
            # 새 캔들 생성
            new_candle = PriceData(
                ticker_id=ticker_id,
                timestamp=minute_ts,
                timeframe="1m",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                source="KIS_REALTIME",
                is_adjusted=False,
            )
            db.add(new_candle)

            logger.debug(
                f"1분봉 생성: ticker_id={ticker_id}, ts={minute_ts}, price={price}"
            )

        await db.commit()

    async def _process_price_event(self, event: PriceEvent) -> None:
        """
        PriceEvent를 받아 DB에 저장
        """
        async for db in get_session():
            try:
                # ticker_id 조회 (캐시 활용)
                cache_key = event.ticker_code
                if cache_key not in self.candle_cache:
                    ticker_id = await self._get_ticker_id(db, event.ticker_code)
                    if not ticker_id:
                        return
                    self.candle_cache[cache_key] = {"ticker_id": ticker_id}

                ticker_id = self.candle_cache[cache_key]["ticker_id"]

                # DB에 저장
                await self._upsert_price_data(
                    db=db,
                    ticker_id=ticker_id,
                    timestamp=event.timestamp,
                    price=event.price,
                    volume=event.volume,
                )

            except Exception as e:
                logger.error(f"PriceEvent 처리 중 오류: {e}", exc_info=True)
                await db.rollback()
            finally:
                break  # get_session()은 자동으로 close

    async def run(self):
        """
        PriceEventBus를 구독하고 이벤트를 DB에 기록
        백그라운드 태스크로 실행됨
        """
        self.is_running = True
        queue = self.event_bus.subscribe()

        logger.info("PriceDataRecorder 시작 - 실시간 시세를 DB에 저장합니다.")

        try:
            while self.is_running:
                try:
                    # 이벤트 수신 대기
                    event: PriceEvent = await queue.get()

                    # DB에 저장
                    await self._process_price_event(event)

                except Exception as e:
                    logger.error(f"PriceDataRecorder 이벤트 처리 오류: {e}", exc_info=True)
                    continue

        except asyncio.CancelledError:
            logger.info("PriceDataRecorder 종료")
            self.is_running = False
            raise
        finally:
            self.event_bus.unsubscribe(queue)

    def stop(self):
        """Recorder 중지"""
        self.is_running = False


# 싱글톤 인스턴스
_recorder: Optional[PriceDataRecorder] = None


def get_price_data_recorder() -> PriceDataRecorder:
    """PriceDataRecorder 싱글톤 반환"""
    global _recorder
    if _recorder is None:
        _recorder = PriceDataRecorder()
    return _recorder
