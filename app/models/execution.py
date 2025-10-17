from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import Column,CheckConstraint
from sqlalchemy.types import Numeric
from sqlalchemy import DateTime
from sqlmodel import Field
from app.models.base import BaseModel


class Execution(BaseModel, table=True):
    """
    체결 정보 (부분체결 포함)
    """

    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_exec_quantity_positive"),
        CheckConstraint("price > 0", name="ck_exec_price_positive"),
    )

    exec_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="체결 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    order_id: int = Field(
        foreign_key="orders.order_id",
        nullable=False,
        description="주문 ID",
    )

    quantity: Decimal = Field(
        sa_column=Column(Numeric(20, 8,asdecimal=True)),
        nullable=False,
        description="체결 수량",
    )

    price: Decimal = Field(
        sa_column=Column(Numeric(20, 8,asdecimal=True)),
        nullable=False,
        description="체결 단가",
    )

    exec_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column=Column(DateTime(timezone=False)),
        description="체결 시각(UTC)",
    )
