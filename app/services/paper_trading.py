"""
Paper Trading Service
모의투자 비즈니스 로직
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading import PaperTradingAccount
from app.models.order import Order, OrderType, OrderSide, OrderStatus
from app.models.position import Position
from app.repositories.paper_trading import (
    PaperTradingRepository,
    OrderRepository,
    PositionRepository,
    ExecutionRepository,
)
from app.repositories.ticker import TickerRepository
from app.models.price_data import PriceData
from sqlalchemy import select, desc


class PaperTradingService:
    """모의투자 서비스"""

    def __init__(self):
        self.account_repo = PaperTradingRepository()
        self.order_repo = OrderRepository()
        self.position_repo = PositionRepository()
        self.execution_repo = ExecutionRepository()
        self.ticker_repo = TickerRepository()

    # ========== 헬퍼 메서드 ==========

    async def _get_latest_price(self, db: AsyncSession, ticker_id: int) -> Optional[Decimal]:
        """
        DB에서 최신 시세를 조회합니다 (1m 캔들 기준)

        Args:
            db: DB 세션
            ticker_id: 티커 ID

        Returns:
            최신 종가 (Decimal) 또는 None
        """
        stmt = (
            select(PriceData.close)
            .where(PriceData.ticker_id == ticker_id)
            .where(PriceData.timeframe == "1m")
            .order_by(desc(PriceData.timestamp))
            .limit(1)
        )
        result = await db.execute(stmt)
        price = result.scalar_one_or_none()
        return price

    # ========== 계좌 관리 ==========

    async def get_or_create_account(
        self, db: AsyncSession, user_id: int, initial_balance: Decimal = Decimal("10000000")
    ) -> PaperTradingAccount:
        """계좌 조회 또는 생성"""
        account = await self.account_repo.get_account_by_user_id(db, user_id)

        if not account:
            account = await self.account_repo.create_account(
                db, user_id, initial_balance
            )
            await db.commit()

        return account

    async def get_account(
        self, db: AsyncSession, user_id: int
    ) -> PaperTradingAccount:
        """계좌 조회"""
        account = await self.account_repo.get_account_by_user_id(db, user_id)
        if not account:
            raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")
        return account

    async def reset_account(
        self, db: AsyncSession, user_id: int
    ) -> PaperTradingAccount:
        """계좌 초기화"""
        account = await self.get_account(db, user_id)
        account = await self.account_repo.reset_account(db, account.account_id)
        await db.commit()
        return account

    async def toggle_account_active(
        self, db: AsyncSession, user_id: int, is_active: bool
    ) -> PaperTradingAccount:
        """계좌 활성화/비활성화 (Kill Switch)"""
        account = await self.get_account(db, user_id)
        account.is_active = is_active
        await self.account_repo.update_account(db, account)
        await db.commit()
        return account

    # ========== 주문 관리 ==========

    async def submit_order(
        self,
        db: AsyncSession,
        user_id: int,
        ticker_code: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None,
        strategy_id: Optional[int] = None,
    ) -> Order:
        """주문 제출"""
        # 1. 계좌 조회
        account = await self.get_account(db, user_id)

        # 2. Kill Switch 확인
        if not account.is_active:
            raise HTTPException(
                status_code=403,
                detail="계좌가 비활성화 상태입니다. Kill Switch를 확인하세요."
            )

        # 3. 종목 ID 조회
        ticker = await self.ticker_repo.get_ticker_by_kis_code(db, ticker_code)
        if not ticker:
            raise HTTPException(
                status_code=404,
                detail=f"종목을 찾을 수 없습니다: {ticker_code}"
            )

        # 4. 주문 검증
        if order_type == OrderType.LIMIT and not limit_price:
            raise HTTPException(
                status_code=400,
                detail="지정가 주문은 limit_price가 필요합니다."
            )

        if side == OrderSide.BUY:
            await self._validate_buy_order(db, account, quantity, limit_price or Decimal("0"))
        else:  # SELL
            await self._validate_sell_order(db, account, ticker.ticker_id, quantity)

        # 5. 주문 생성
        order = Order(
            account_id=account.account_id,
            ticker_id=ticker.ticker_id,
            strategy_id=strategy_id,
            order_type=order_type,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            status=OrderStatus.PENDING,
            submitted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        order = await self.order_repo.create_order(db, order)
        await db.commit()

        return order

    async def cancel_order(
        self, db: AsyncSession, user_id: int, order_id: int
    ) -> Order:
        """주문 취소"""
        order = await self.order_repo.get_order_by_id(db, order_id)

        if not order:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")

        # 주문 소유권 확인
        account = await self.account_repo.get_account_by_id(db, order.account_id)
        if not account or account.user_id != user_id:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        # PENDING 상태만 취소 가능
        if order.status != OrderStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"취소할 수 없는 주문 상태입니다: {order.status}"
            )

        order = await self.order_repo.cancel_order(db, order_id)
        await db.commit()

        return order

    async def get_orders(
        self, db: AsyncSession, user_id: int, limit: int = 100
    ) -> List[Order]:
        """주문 목록 조회"""
        account = await self.get_account(db, user_id)
        return await self.order_repo.get_orders_by_account(db, account.account_id, limit)

    # ========== 포지션 관리 ==========

    async def get_positions(
        self, db: AsyncSession, user_id: int
    ) -> List[Position]:
        """보유 포지션 조회"""
        account = await self.get_account(db, user_id)
        return await self.position_repo.get_positions_by_account(db, account.account_id)

    async def get_balance(
        self, db: AsyncSession, user_id: int
    ) -> dict:
        """잔고 및 자산 평가 (실시간 시세 반영)"""
        account = await self.get_account(db, user_id)
        positions = await self.position_repo.get_positions_by_account(db, account.account_id)

        # 포지션 평가액 계산 (실시간 시세 반영)
        total_position_value = Decimal("0")

        for pos in positions:
            # DB에서 최신 가격 조회 (1m 캔들)
            latest_price = await self._get_latest_price(db, pos.ticker_id)

            # 최신 가격이 없으면 평균 매입가 사용
            current_price = latest_price if latest_price is not None else pos.average_buy_price

            total_position_value += pos.quantity * current_price

        return {
            "account_id": account.account_id,
            "current_balance": float(account.current_balance),
            "total_position_value": float(total_position_value),
            "total_asset_value": float(account.current_balance + total_position_value),
            "initial_balance": float(account.initial_balance),
            "profit_loss": float(
                account.current_balance + total_position_value - account.initial_balance
            ),
            "is_active": account.is_active,
        }

    # ========== 주문 검증 ==========

    async def _validate_buy_order(
        self, db: AsyncSession, account: PaperTradingAccount,
        quantity: Decimal, price: Decimal
    ) -> None:
        """매수 주문 검증 (잔고 확인)"""
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="수량은 0보다 커야 합니다.")

        # 시장가 주문은 체결 시점에 검증
        if price > 0:
            required_amount = quantity * price

            if account.current_balance < required_amount:
                raise HTTPException(
                    status_code=400,
                    detail=f"잔고 부족 (필요: {required_amount}, 보유: {account.current_balance})"
                )

    async def _validate_sell_order(
        self, db: AsyncSession, account: PaperTradingAccount,
        ticker_id: int, quantity: Decimal
    ) -> None:
        """매도 주문 검증 (보유 수량 확인)"""
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="수량은 0보다 커야 합니다.")

        position = await self.position_repo.get_position(
            db, account.account_id, ticker_id
        )

        if not position or position.quantity < quantity:
            held = position.quantity if position else Decimal("0")
            raise HTTPException(
                status_code=400,
                detail=f"보유 수량 부족 (필요: {quantity}, 보유: {held})"
            )
