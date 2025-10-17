from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel


class Trade(BaseModel, table=True):
    """
    공통 거래 로그
    - 백테스트 거래 / 실시간 거래 모두 기록
    """

    __tablename__ = "trades"

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

    side: str = Field(
        max_length=10,
        nullable=False,
        description="BUY / SELL",
    )

    quantity: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="거래 수량",
    )

    price: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="거래 단가",
    )

    transaction_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        description="거래 시각(UTC)",
    )
