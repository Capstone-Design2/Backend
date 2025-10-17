from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from enum import Enum

from sqlalchemy import Column,CheckConstraint
from sqlalchemy.types import Numeric
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME
from sqlmodel import Field
from app.models.base import BaseModel


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class Trade(BaseModel, table=True):
    """
    공통 거래 로그
    - 백테스트 거래 / 실시간 거래 모두 기록
    """

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_trade_quantity_positive"),
        CheckConstraint("price > 0", name="ck_trade_price_positive"),
    )

    trade_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="거래 로그 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    # 백테스트 연결 (옵션)
    result_id: Optional[int] = Field(
        default=None,
        foreign_key="backtest_results.result_id",
        description="백테스트 결과 ID",
    )

    # 실시간 연결 (옵션)
    account_id: Optional[int] = Field(
        default=None,
        foreign_key="paper_trading_accounts.account_id",
        description="계좌 ID",
    )

    order_id: Optional[int] = Field(
        default=None,
        foreign_key="orders.order_id",
        description="주문 ID",
    )

    exec_id: Optional[int] = Field(
        default=None,
        foreign_key="executions.exec_id",
        description="체결 ID",
    )

    ticker_id: int = Field(
        foreign_key="tickers.ticker_id",
        nullable=False,
        description="종목 ID",
    )

    side: TradeSide = Field(
        nullable=False,
        description="매도/매수 구분",
    )

    quantity: Decimal = Field(
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        nullable=False,
        description="거래 수량",
    )

    price: Decimal = Field(
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        nullable=False,
        description="거래 단가",
    )

    transaction_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column=Column(MYSQL_DATETIME(fsp=6)),
        description="거래 시각(UTC)",
    )
