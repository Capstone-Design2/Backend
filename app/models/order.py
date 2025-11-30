from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from decimal import Decimal

from sqlalchemy import Column,CheckConstraint
from sqlalchemy.types import Numeric
from sqlalchemy import DateTime
from sqlmodel import Field
from app.models.base import BaseModel


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"


class Order(BaseModel, table=True):
    """
    주문 정보
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_quantity_positive"),
    )

    order_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="주문 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    account_id: int = Field(
        foreign_key="paper_trading_accounts.account_id",
        nullable=False,
        description="계좌 ID",
    )

    ticker_id: int = Field(
        foreign_key="tickers.ticker_id",
        nullable=False,
        description="종목 ID",
    )

    strategy_id: Optional[int] = Field(
        default=None,
        foreign_key="strategies.strategy_id",
        description="유발 전략(선택)",
    )

    order_type: OrderType = Field(
        default=OrderType.MARKET,
        description="주문 유형",
    )

    side: OrderSide = Field(
        default=OrderSide.BUY,
        description="매수/매도",
    )

    quantity: Decimal = Field(
        sa_column=Column(Numeric(20, 8, asdecimal=True), nullable=False),
        description="주문 수량",
    )

    limit_price: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        description="지정가",
    )

    status: OrderStatus = Field(
        default=OrderStatus.PENDING,
        description="주문 상태",
    )

    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column=Column(DateTime(timezone=False), nullable=False),
        description="주문 접수 시각(UTC)",
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=False)),
        description="주문 체결 완료 시각(UTC)",
    )
