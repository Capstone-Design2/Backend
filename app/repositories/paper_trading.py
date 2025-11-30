"""
Paper Trading Repository
모의투자 관련 DB 쿼리
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from datetime import datetime, timezone

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.paper_trading import PaperTradingAccount
from app.models.order import Order, OrderStatus, OrderSide
from app.models.position import Position
from app.models.execution import Execution


class PaperTradingRepository:
    """모의투자 계좌 Repository"""

    async def get_account_by_user_id(
        self, db: AsyncSession, user_id: int
    ) -> Optional[PaperTradingAccount]:
        """사용자 ID로 계좌 조회"""
        stmt = select(PaperTradingAccount).where(PaperTradingAccount.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_account_by_id(
        self, db: AsyncSession, account_id: int
    ) -> Optional[PaperTradingAccount]:
        """계좌 ID로 조회"""
        stmt = select(PaperTradingAccount).where(
            PaperTradingAccount.account_id == account_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_account(
        self, db: AsyncSession, user_id: int, initial_balance: Decimal
    ) -> PaperTradingAccount:
        """계좌 생성"""
        account = PaperTradingAccount(
            user_id=user_id,
            initial_balance=initial_balance,
            current_balance=initial_balance,
            total_asset_value=initial_balance,
            is_active=True,
        )
        db.add(account)
        await db.flush()
        await db.refresh(account)
        return account

    async def update_account(
        self, db: AsyncSession, account: PaperTradingAccount
    ) -> PaperTradingAccount:
        """계좌 정보 업데이트"""
        await db.flush()
        await db.refresh(account)
        return account

    async def reset_account(
        self, db: AsyncSession, account_id: int
    ) -> PaperTradingAccount:
        """계좌 초기화 (잔고 리셋, 포지션 삭제)"""
        account = await self.get_account_by_id(db, account_id)
        if not account:
            raise ValueError(f"계좌를 찾을 수 없습니다: {account_id}")

        # 포지션 삭제
        await db.execute(
            delete(Position).where(Position.account_id == account_id)
        )

        # 잔고 초기화
        account.current_balance = account.initial_balance
        account.total_asset_value = account.initial_balance
        await db.flush()
        await db.refresh(account)
        return account


class OrderRepository:
    """주문 Repository"""

    async def create_order(self, db: AsyncSession, order: Order) -> Order:
        """주문 생성"""
        db.add(order)
        await db.flush()
        await db.refresh(order)
        return order

    async def get_order_by_id(
        self, db: AsyncSession, order_id: int
    ) -> Optional[Order]:
        """주문 ID로 조회"""
        stmt = select(Order).where(Order.order_id == order_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_orders_by_account(
        self, db: AsyncSession, account_id: int, limit: int = 100
    ) -> List[Order]:
        """계좌의 주문 목록 조회 (최신순)"""
        stmt = (
            select(Order)
            .where(Order.account_id == account_id)
            .order_by(Order.submitted_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_orders(
        self, db: AsyncSession
    ) -> List[Order]:
        """모든 PENDING 상태 주문 조회"""
        stmt = select(Order).where(Order.status == OrderStatus.PENDING)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_orders_by_ticker(
        self, db: AsyncSession, ticker_id: int
    ) -> List[Order]:
        """특정 종목의 PENDING 주문 조회"""
        stmt = select(Order).where(
            Order.ticker_id == ticker_id,
            Order.status == OrderStatus.PENDING
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_order_status(
        self, db: AsyncSession, order_id: int, status: OrderStatus,
        completed_at: Optional[datetime] = None
    ) -> Order:
        """주문 상태 업데이트"""
        order = await self.get_order_by_id(db, order_id)
        if not order:
            raise ValueError(f"주문을 찾을 수 없습니다: {order_id}")

        order.status = status
        if completed_at:
            order.completed_at = completed_at

        await db.flush()
        await db.refresh(order)
        return order

    async def cancel_order(self, db: AsyncSession, order_id: int) -> Order:
        """주문 취소"""
        return await self.update_order_status(
            db, order_id, OrderStatus.CANCELED,
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )


class PositionRepository:
    """포지션 Repository"""

    async def get_position(
        self, db: AsyncSession, account_id: int, ticker_id: int
    ) -> Optional[Position]:
        """포지션 조회"""
        stmt = select(Position).where(
            Position.account_id == account_id,
            Position.ticker_id == ticker_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_positions_by_account(
        self, db: AsyncSession, account_id: int
    ) -> List[Position]:
        """계좌의 모든 포지션 조회"""
        stmt = select(Position).where(Position.account_id == account_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_position(
        self, db: AsyncSession, position: Position
    ) -> Position:
        """포지션 생성 또는 업데이트"""
        existing = await self.get_position(
            db, position.account_id, position.ticker_id
        )

        if existing:
            existing.quantity = position.quantity
            existing.average_buy_price = position.average_buy_price
            await db.flush()
            await db.refresh(existing)
            return existing
        else:
            db.add(position)
            await db.flush()
            await db.refresh(position)
            return position

    async def delete_position(
        self, db: AsyncSession, position_id: int
    ) -> None:
        """포지션 삭제"""
        await db.execute(
            delete(Position).where(Position.position_id == position_id)
        )
        await db.flush()


class ExecutionRepository:
    """체결 Repository"""

    async def create_execution(
        self, db: AsyncSession, execution: Execution
    ) -> Execution:
        """체결 기록 생성"""
        db.add(execution)
        await db.flush()
        await db.refresh(execution)
        return execution

    async def get_executions_by_order(
        self, db: AsyncSession, order_id: int
    ) -> List[Execution]:
        """주문의 체결 내역 조회"""
        stmt = select(Execution).where(Execution.order_id == order_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())
