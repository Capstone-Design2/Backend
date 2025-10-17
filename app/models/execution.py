from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel


class Execution(BaseModel, table=True):
    """
    체결 정보 (부분체결 포함)
    """

    __tablename__ = "executions"

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

    quantity: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="체결 수량",
    )

    price: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="체결 단가",
    )

    exec_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        description="체결 시각(UTC)",
    )
