"""
PriceEventBus - 실시간 시세 이벤트 Pub/Sub 시스템
asyncio.Queue 기반으로 KIS WebSocket과 다중 컨슈머를 연결
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class PriceEvent:
    """실시간 시세 이벤트"""
    ticker_code: str
    price: Decimal
    volume: int
    timestamp: datetime
    change: Decimal = Decimal("0")
    change_rate: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        """JSON 직렬화를 위한 딕셔너리 변환"""
        return {
            "ticker_code": self.ticker_code,
            "price": float(self.price),
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "change": float(self.change),
            "change_rate": float(self.change_rate),
        }


class PriceEventBus:
    """
    실시간 시세 이벤트 버스
    - KIS WebSocket Client가 publish
    - FastAPI WebSocket Endpoint와 Order Executor가 subscribe
    """

    def __init__(self, max_queue_size: int = 1000):
        """
        Args:
            max_queue_size: 각 subscriber queue의 최대 크기
        """
        self._subscribers: List[asyncio.Queue] = []
        self._max_queue_size = max_queue_size
        self._event_count = 0

    async def publish(self, event: PriceEvent) -> None:
        """
        이벤트를 모든 subscriber에게 전달

        Args:
            event: 발행할 PriceEvent
        """
        self._event_count += 1

        if not self._subscribers:
            logger.debug(f"구독자 없음, 이벤트 무시: {event.ticker_code}")
            return

        # 모든 subscriber의 queue에 이벤트 추가
        for queue in self._subscribers:
            try:
                # 큐가 가득 찬 경우 대기하지 않고 로그만 남김
                if queue.full():
                    logger.warning(
                        f"Queue 가득 참 (size={queue.qsize()}), "
                        f"이벤트 드롭: {event.ticker_code}"
                    )
                    continue

                queue.put_nowait(event)

            except asyncio.QueueFull:
                logger.warning(f"Queue 가득 참, 이벤트 드롭: {event.ticker_code}")
            except Exception as e:
                logger.error(f"이벤트 발행 실패: {e}", exc_info=True)

        logger.debug(
            f"이벤트 발행 완료 (구독자 {len(self._subscribers)}명): "
            f"{event.ticker_code} @ {event.price}"
        )

    def subscribe(self) -> asyncio.Queue[PriceEvent]:
        """
        새로운 subscriber 등록

        Returns:
            이벤트를 수신할 Queue
        """
        queue: asyncio.Queue[PriceEvent] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.append(queue)
        logger.info(f"새 구독자 등록 (총 {len(self._subscribers)}명)")
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        subscriber 등록 해제

        Args:
            queue: 등록 해제할 Queue
        """
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            logger.info(f"구독자 해제 (남은 구독자: {len(self._subscribers)}명)")

    def get_subscriber_count(self) -> int:
        """현재 구독자 수 반환"""
        return len(self._subscribers)

    def get_event_count(self) -> int:
        """총 발행된 이벤트 수 반환"""
        return self._event_count

    def clear_stats(self) -> None:
        """통계 초기화"""
        self._event_count = 0


# 싱글톤 인스턴스
_price_event_bus: Optional[PriceEventBus] = None


def get_price_event_bus() -> PriceEventBus:
    """PriceEventBus 싱글톤 반환"""
    global _price_event_bus
    if _price_event_bus is None:
        _price_event_bus = PriceEventBus()
    return _price_event_bus
