from typing import Optional
from decimal import Decimal
from sqlalchemy import Column, UniqueConstraint, CheckConstraint
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel


class Position(BaseModel, table=True):
    """
    보유 포지션 (계좌/종목)
    """

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "ticker_id", name="uq_position_account_ticker"),
        CheckConstraint("quantity > 0", name="ck_pos_quantity_positive"),
        CheckConstraint("average_buy_price > 0", name="ck_pos_avg_buy_price_positive"),
    )

    position_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="포지션 ID",
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

    quantity: Decimal = Field(
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        nullable=False,
        description="현재 수량",
    )

    average_buy_price: Decimal = Field(
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        nullable=False,
        description="평균 매입 단가",
    )
