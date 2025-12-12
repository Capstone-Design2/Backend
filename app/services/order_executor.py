"""
Order Execution Engine
실시간 시세 기반 자동 주문 체결
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import get_price_event_bus, PriceEvent
from app.database import get_session
from app.models.order import Order, OrderType, OrderSide, OrderStatus
from app.models.position import Position
from app.models.execution import Execution
from app.repositories.paper_trading import (
    OrderRepository,
    PositionRepository,
    ExecutionRepository,
    PaperTradingRepository,
)
from app.repositories.ticker import TickerRepository

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    주문 자동 체결 엔진
    - PriceEventBus에서 실시간 시세 수신
    - PENDING 주문 조회
    - 체결 조건 확인 후 체결 처리
    """

    def __init__(self):
        self.event_bus = get_price_event_bus()
        self.order_repo = OrderRepository()
        self.position_repo = PositionRepository()
        self.execution_repo = ExecutionRepository()
        self.account_repo = PaperTradingRepository()
        self.ticker_repo = TickerRepository()

        # 종목 코드 → ticker_id 캐시
        self.ticker_cache: dict[str, int] = {}

    async def run(self):
        """
        실행 루프
        백그라운드 태스크로 main.py lifespan에서 실행됨
        """
        price_queue = self.event_bus.subscribe()
        logger.info("Order Executor 시작")

        try:
            while True:
                # 실시간 시세 이벤트 수신
                event: PriceEvent = await price_queue.get()

                # 해당 종목의 PENDING 주문 체결 처리
                await self._process_price_event(event)

        except asyncio.CancelledError:
            logger.info("Order Executor 종료")
            self.event_bus.unsubscribe(price_queue)
        except Exception as e:
            logger.error(f"Order Executor 오류: {e}", exc_info=True)

    async def _process_price_event(self, event: PriceEvent) -> None:
        """
        시세 이벤트 처리: PENDING 주문 조회 및 체결
        """
        try:
            # ticker_id 조회 (캐시 활용)
            ticker_id = await self._get_ticker_id(event.ticker_code)

            if not ticker_id:
                logger.debug(f"ticker_id를 찾을 수 없음: {event.ticker_code}")
                return

            # DB 세션 생성
            async for db in get_session():
                try:
                    # PENDING 주문 조회
                    pending_orders = await self.order_repo.get_pending_orders_by_ticker(
                        db, ticker_id
                    )

                    if not pending_orders:
                        return

                    logger.debug(
                        f"{event.ticker_code} PENDING 주문 {len(pending_orders)}건 발견"
                    )

                    # 각 주문 체결 조건 확인
                    for order in pending_orders:
                        if self._should_fill(order, event.price):
                            await self._fill_order(db, order, event.price)

                    await db.commit()

                except Exception as e:
                    await db.rollback()
                    logger.error(f"주문 체결 처리 중 오류: {e}", exc_info=True)
                finally:
                    break  # 첫 번째 세션만 사용

        except Exception as e:
            logger.error(f"시세 이벤트 처리 오류: {e}", exc_info=True)

    def _should_fill(self, order: Order, current_price: Decimal) -> bool:
        """
        체결 조건 확인

        Args:
            order: 주문 객체
            current_price: 현재가

        Returns:
            체결 여부
        """
        if order.order_type == OrderType.MARKET:
            # 시장가는 즉시 체결
            return True

        elif order.order_type == OrderType.LIMIT:
            # 지정가: 가격 조건 확인
            if order.side == OrderSide.BUY:
                # 매수: 현재가 <= 지정가
                return current_price <= order.limit_price
            else:  # SELL
                # 매도: 현재가 >= 지정가
                return current_price >= order.limit_price

        # STOP 주문 등 향후 확장
        return False

    async def _fill_order(
        self, db: AsyncSession, order: Order, price: Decimal
    ) -> None:
        """
        주문 체결 처리

        Args:
            db: DB 세션
            order: 주문 객체
            price: 체결 가격
        """
        try:
            logger.info(
                f"주문 체결 시작: order_id={order.order_id}, "
                f"side={order.side}, qty={order.quantity}, price={price}"
            )

            # 1. 잔고 재검증 (매수 시)
            if order.side == OrderSide.BUY:
                account = await self.account_repo.get_account_by_id(
                    db, order.account_id
                )
                required_amount = order.quantity * price

                if account.current_balance < required_amount:
                    logger.warning(
                        f"잔고 부족으로 주문 취소: order_id={order.order_id}"
                    )
                    await self.order_repo.cancel_order(db, order.order_id)
                    return

            # 2. 포지션 재검증 (매도 시)
            if order.side == OrderSide.SELL:
                position = await self.position_repo.get_position(
                    db, order.account_id, order.ticker_id
                )

                if not position or position.quantity < order.quantity:
                    logger.warning(
                        f"보유 수량 부족으로 주문 취소: order_id={order.order_id}"
                    )
                    await self.order_repo.cancel_order(db, order.order_id)
                    return

            # 3. Execution 레코드 생성
            execution = Execution(
                order_id=order.order_id,
                quantity=order.quantity,
                price=price,
                exec_time=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            await self.execution_repo.create_execution(db, execution)

            # 4. Order 상태 업데이트
            await self.order_repo.update_order_status(
                db,
                order.order_id,
                OrderStatus.FILLED,
                completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

            # 5. Position 업데이트
            await self._update_position(db, order, price)

            # 6. Account balance 업데이트
            await self._update_balance(db, order, price)

            logger.info(f"주문 체결 완료: order_id={order.order_id}")

        except Exception as e:
            logger.error(f"주문 체결 실패: {e}", exc_info=True)
            raise

    async def _update_position(
        self, db: AsyncSession, order: Order, price: Decimal
    ) -> None:
        """
        포지션 업데이트

        Args:
            db: DB 세션
            order: 주문 객체
            price: 체결 가격
        """
        position = await self.position_repo.get_position(
            db, order.account_id, order.ticker_id
        )

        if order.side == OrderSide.BUY:
            # 매수: 평균 단가 재계산
            if position:
                total_cost = (
                    position.average_buy_price * position.quantity
                    + price * order.quantity
                )
                total_qty = position.quantity + order.quantity
                position.quantity = total_qty
                position.average_buy_price = total_cost / total_qty
            else:
                # 신규 포지션
                position = Position(
                    account_id=order.account_id,
                    ticker_id=order.ticker_id,
                    quantity=order.quantity,
                    average_buy_price=price,
                )

            await self.position_repo.upsert_position(db, position)

        else:  # SELL
            # 매도: 수량 차감
            if not position:
                raise RuntimeError(f"포지션 없음: ticker_id={order.ticker_id}")

            position.quantity -= order.quantity

            # Decimal 비교는 정확한 0과 비교하거나, 매우 작은 값과 비교
            if position.quantity <= Decimal('0.00000001'):
                # 수량이 0 또는 음수이면 삭제 (부동소수점 오차 고려)
                # expunge를 통해 세션에서 제거하여 autoflush 방지
                db.expunge(position)
                await self.position_repo.delete_position(db, position.position_id)
            else:
                await self.position_repo.upsert_position(db, position)

    async def _update_balance(
        self, db: AsyncSession, order: Order, price: Decimal
    ) -> None:
        """
        계좌 잔고 업데이트

        Args:
            db: DB 세션
            order: 주문 객체
            price: 체결 가격
        """
        account = await self.account_repo.get_account_by_id(db, order.account_id)

        if not account:
            raise RuntimeError(f"계좌 없음: account_id={order.account_id}")

        if order.side == OrderSide.BUY:
            # 매수: 잔고 차감
            account.current_balance -= price * order.quantity
        else:  # SELL
            # 매도: 잔고 증가
            account.current_balance += price * order.quantity

        await self.account_repo.update_account(db, account)

    async def _get_ticker_id(self, ticker_code: str) -> int | None:
        """
        ticker_code → ticker_id 변환 (캐시 활용)

        Args:
            ticker_code: 종목 코드 (예: 005930)

        Returns:
            ticker_id 또는 None
        """
        if ticker_code in self.ticker_cache:
            return self.ticker_cache[ticker_code]

        # DB 조회
        async for db in get_session():
            try:
                ticker = await self.ticker_repo.get_ticker_by_kis_code(
                    db, ticker_code
                )
                if ticker:
                    self.ticker_cache[ticker_code] = ticker.ticker_id
                    return ticker.ticker_id
            finally:
                break

        return None


# 싱글톤 인스턴스
_order_executor: OrderExecutor | None = None


def get_order_executor() -> OrderExecutor:
    """Order Executor 싱글톤 반환"""
    global _order_executor
    if _order_executor is None:
        _order_executor = OrderExecutor()
    return _order_executor
