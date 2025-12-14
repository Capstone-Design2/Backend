"""
Paper Trading API Router
모의투자 REST API 엔드포인트
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.order import OrderType, OrderSide
from app.services.paper_trading import PaperTradingService
from app.utils.dependencies import get_current_user
from app.utils.router import get_router
from types import SimpleNamespace

router = get_router("paper-trading")


# ========== Pydantic Schemas ==========

class AccountCreateRequest(BaseModel):
    initial_balance: Decimal = Field(
        default=Decimal("10000000"),
        description="초기 예수금",
        ge=0
    )


class AccountResponse(BaseModel):
    account_id: int
    user_id: int
    initial_balance: float
    current_balance: float
    total_asset_value: float
    is_active: bool


class OrderCreateRequest(BaseModel):
    ticker_code: str = Field(..., description="종목 코드 (예: 005930)")
    side: OrderSide = Field(..., description="매수/매도")
    quantity: Decimal = Field(..., description="수량", gt=0)
    order_type: OrderType = Field(default=OrderType.MARKET, description="주문 유형")
    limit_price: Optional[Decimal] = Field(None, description="지정가", gt=0)
    strategy_id: Optional[int] = Field(None, description="전략 ID (선택)")


class OrderResponse(BaseModel):
    order_id: int
    account_id: int
    ticker_id: int
    strategy_id: Optional[int]
    order_type: str
    side: str
    quantity: float
    limit_price: Optional[float]
    status: str
    submitted_at: str
    completed_at: Optional[str]


class PositionResponse(BaseModel):
    position_id: int
    account_id: int
    ticker_id: int
    ticker_code: Optional[str] = None
    quantity: float
    average_buy_price: float
    current_price: Optional[float] = None
    position_value: Optional[float] = None
    profit_loss: Optional[float] = None
    profit_loss_rate: Optional[float] = None


class BalanceResponse(BaseModel):
    account_id: int
    current_balance: float
    total_position_value: float
    total_asset_value: float
    initial_balance: float
    profit_loss: float
    is_active: bool


# ========== 의존성 ==========

def get_paper_trading_service() -> PaperTradingService:
    return PaperTradingService()


# ========== API 엔드포인트 ==========

@router.post(
    "/account",
    response_model=AccountResponse,
    summary="모의투자 계좌 생성",
    description="사용자의 모의투자 계좌를 생성합니다. 이미 존재하면 기존 계좌를 반환합니다."
)
async def create_account(
    request: AccountCreateRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    account = await service.get_or_create_account(
        db, current_user.user_id, request.initial_balance
    )
    return AccountResponse(
        account_id=account.account_id,
        user_id=account.user_id,
        initial_balance=float(account.initial_balance),
        current_balance=float(account.current_balance),
        total_asset_value=float(account.total_asset_value),
        is_active=account.is_active,
    )


@router.get(
    "/account",
    response_model=AccountResponse,
    summary="모의투자 계좌 조회",
    description="현재 사용자의 모의투자 계좌 정보를 조회합니다."
)
async def get_account(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    account = await service.get_account(db, current_user.user_id)
    return AccountResponse(
        account_id=account.account_id,
        user_id=account.user_id,
        initial_balance=float(account.initial_balance),
        current_balance=float(account.current_balance),
        total_asset_value=float(account.total_asset_value),
        is_active=account.is_active,
    )


@router.post(
    "/account/reset",
    response_model=AccountResponse,
    summary="모의투자 계좌 초기화",
    description="계좌 잔고를 초기 예수금으로 리셋하고 모든 포지션을 삭제합니다."
)
async def reset_account(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    account = await service.reset_account(db, current_user.user_id)
    return AccountResponse(
        account_id=account.account_id,
        user_id=account.user_id,
        initial_balance=float(account.initial_balance),
        current_balance=float(account.current_balance),
        total_asset_value=float(account.total_asset_value),
        is_active=account.is_active,
    )


@router.patch(
    "/account/toggle",
    response_model=AccountResponse,
    summary="계좌 활성화/비활성화 (Kill Switch)",
    description="모의투자 계좌의 활성화 상태를 토글합니다."
)
async def toggle_account(
    is_active: Annotated[bool, Query(description="활성화 여부")],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    account = await service.toggle_account_active(db, current_user.user_id, is_active)
    return AccountResponse(
        account_id=account.account_id,
        user_id=account.user_id,
        initial_balance=float(account.initial_balance),
        current_balance=float(account.current_balance),
        total_asset_value=float(account.total_asset_value),
        is_active=account.is_active,
    )


@router.post(
    "/order",
    response_model=OrderResponse,
    summary="주문 제출",
    description="매수/매도 주문을 제출합니다. MARKET 또는 LIMIT 주문을 지원합니다."
)
async def submit_order(
    request: OrderCreateRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    order = await service.submit_order(
        db,
        user_id=current_user.user_id,
        ticker_code=request.ticker_code,
        side=request.side,
        quantity=request.quantity,
        order_type=request.order_type,
        limit_price=request.limit_price,
        strategy_id=request.strategy_id,
    )

    return OrderResponse(
        order_id=order.order_id,
        account_id=order.account_id,
        ticker_id=order.ticker_id,
        strategy_id=order.strategy_id,
        order_type=order.order_type.value,
        side=order.side.value,
        quantity=float(order.quantity),
        limit_price=float(order.limit_price) if order.limit_price else None,
        status=order.status.value,
        submitted_at=order.submitted_at.isoformat(),
        completed_at=order.completed_at.isoformat() if order.completed_at else None,
    )


@router.delete(
    "/order/{order_id}",
    response_model=OrderResponse,
    summary="주문 취소",
    description="PENDING 상태의 주문을 취소합니다."
)
async def cancel_order(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    order = await service.cancel_order(db, current_user.user_id, order_id)

    return OrderResponse(
        order_id=order.order_id,
        account_id=order.account_id,
        ticker_id=order.ticker_id,
        strategy_id=order.strategy_id,
        order_type=order.order_type.value,
        side=order.side.value,
        quantity=float(order.quantity),
        limit_price=float(order.limit_price) if order.limit_price else None,
        status=order.status.value,
        submitted_at=order.submitted_at.isoformat(),
        completed_at=order.completed_at.isoformat() if order.completed_at else None,
    )


@router.get(
    "/orders",
    response_model=list[OrderResponse],
    summary="주문 목록 조회",
    description="사용자의 주문 내역을 조회합니다 (최신순)."
)
async def get_orders(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
    limit: Annotated[int, Query(description="조회 개수", ge=1, le=500)] = 100,
):
    orders = await service.get_orders(db, current_user.user_id, limit)

    return [
        OrderResponse(
            order_id=order.order_id,
            account_id=order.account_id,
            ticker_id=order.ticker_id,
            strategy_id=order.strategy_id,
            order_type=order.order_type.value,
            side=order.side.value,
            quantity=float(order.quantity),
            limit_price=float(order.limit_price) if order.limit_price else None,
            status=order.status.value,
            submitted_at=order.submitted_at.isoformat(),
            completed_at=order.completed_at.isoformat() if order.completed_at else None,
        )
        for order in orders
    ]


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="보유 포지션 조회",
    description="현재 보유 중인 종목 포지션을 조회합니다."
)
async def get_positions(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    from app.repositories.ticker import TickerRepository
    from app.models.price_data import PriceData
    from sqlalchemy import select, desc

    positions = await service.get_positions(db, current_user.user_id)
    ticker_repo = TickerRepository()

    result = []
    for pos in positions:
        # Ticker 정보 조회
        ticker = await ticker_repo.get_symbol_by_id(pos.ticker_id, db)
        ticker_code = ticker.kis_code if ticker else None

        # 실시간 가격 조회 (DB에서 최신 1m 캔들)
        stmt = (
            select(PriceData.close)
            .where(PriceData.ticker_id == pos.ticker_id)
            .where(PriceData.timeframe == "1m")
            .order_by(desc(PriceData.timestamp))
            .limit(1)
        )
        price_result = await db.execute(stmt)
        latest_price = price_result.scalar_one_or_none()

        # 현재가 계산 (실시간 가격이 없으면 평균 매입가 사용)
        current_price = float(latest_price) if latest_price is not None else float(pos.average_buy_price)
        position_value = float(pos.quantity) * current_price
        avg_buy_value = float(pos.quantity * pos.average_buy_price)
        profit_loss = position_value - avg_buy_value
        profit_loss_rate = (profit_loss / avg_buy_value * 100) if avg_buy_value > 0 else 0.0

        result.append(PositionResponse(
            position_id=pos.position_id,
            account_id=pos.account_id,
            ticker_id=pos.ticker_id,
            ticker_code=ticker_code,
            quantity=float(pos.quantity),
            average_buy_price=float(pos.average_buy_price),
            current_price=current_price,
            position_value=position_value,
            profit_loss=profit_loss,
            profit_loss_rate=profit_loss_rate,
        ))

    return result


@router.get(
    "/balance",
    response_model=BalanceResponse,
    summary="잔고 조회",
    description="현재 잔고 및 총 자산 평가액을 조회합니다."
)
async def get_balance(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[SimpleNamespace, Depends(get_current_user)],
    service: Annotated[PaperTradingService, Depends(get_paper_trading_service)],
):
    balance_data = await service.get_balance(db, current_user.user_id)
    return BalanceResponse(**balance_data)
