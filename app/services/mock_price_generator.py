"""
Mock Price Generator
테스트용 가짜 실시간 시세 생성기
KIS WebSocket 연결 실패 시 대체용
"""
import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import List
import random

from app.core.events import get_price_event_bus, PriceEvent

logger = logging.getLogger(__name__)


class MockPriceGenerator:
    """
    테스트용 시세 생성기
    랜덤한 가격 변동으로 실시간 시세 시뮬레이션
    """

    def __init__(self, tickers: List[str], base_prices: dict[str, Decimal] = None):
        """
        Args:
            tickers: 종목 코드 리스트 (예: ['005930', '000660'])
            base_prices: 종목별 기준 가격 (없으면 기본값 사용)
        """
        self.event_bus = get_price_event_bus()
        self.tickers = tickers
        self.is_running = False

        # 기준 가격 설정 (없으면 기본값)
        self.base_prices = base_prices or {
            '005930': Decimal('84000'),  # 삼성전자
            '000660': Decimal('190000'),  # SK하이닉스
        }

        # 현재 가격 (변동 추적용)
        self.current_prices = self.base_prices.copy()

    async def run(self, interval: float = 2.0):
        """
        시세 생성 루프 실행

        Args:
            interval: 시세 발생 간격 (초)
        """
        self.is_running = True
        logger.info(f"Mock Price Generator 시작 (종목: {', '.join(self.tickers)})")

        try:
            while self.is_running:
                for ticker in self.tickers:
                    if ticker not in self.current_prices:
                        # 기준 가격이 없으면 기본값 사용
                        self.current_prices[ticker] = Decimal('100000')

                    # 랜덤 변동 (-0.5% ~ +0.5%)
                    base = self.current_prices[ticker]
                    change_rate = Decimal(str(random.uniform(-0.005, 0.005)))
                    change = base * change_rate
                    new_price = base + change

                    # 가격이 0 이하로 떨어지지 않도록
                    if new_price <= 0:
                        new_price = base
                        change = Decimal('0')
                        change_rate = Decimal('0')

                    self.current_prices[ticker] = new_price

                    # PriceEvent 생성 및 발행
                    event = PriceEvent(
                        ticker_code=ticker,
                        price=new_price,
                        volume=random.randint(100, 10000),
                        timestamp=datetime.now(timezone.utc),
                        change=change,
                        change_rate=change_rate,
                    )

                    await self.event_bus.publish(event)
                    logger.debug(
                        f"Mock 시세 발행: {ticker} = {new_price:.2f} "
                        f"({change:+.2f}, {change_rate*100:+.2f}%)"
                    )

                # 대기
                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("Mock Price Generator 종료")
            self.is_running = False
            raise  # CancelledError는 반드시 재발생
        except Exception as e:
            logger.error(f"Mock Price Generator 오류: {e}", exc_info=True)
            self.is_running = False
            raise  # 예외 재발생

    def stop(self):
        """생성기 중지"""
        self.is_running = False


# 싱글톤 인스턴스
_mock_generator: MockPriceGenerator | None = None


def get_mock_price_generator(
    tickers: List[str] = None,
    base_prices: dict[str, Decimal] = None
) -> MockPriceGenerator:
    """Mock Price Generator 싱글톤 반환"""
    global _mock_generator
    if _mock_generator is None:
        default_tickers = tickers or ['005930', '000660']
        _mock_generator = MockPriceGenerator(default_tickers, base_prices)
    return _mock_generator
