from typing import Optional
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, UniqueConstraint
from sqlmodel import Field
from app.models.base import BaseModel


class Strategy(BaseModel, table=True):
    """
    트레이딩 전략
    - rules: JSON (조건/진입/청산 규칙 등)
    """

    __tablename__ = "strategies"
    __table_args__ = (
    UniqueConstraint("user_id", "strategy_name", name="uq_strategy_user_name"),
)

    strategy_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="전략 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    user_id: int = Field(
        foreign_key="users.user_id",
        nullable=False,
        description="소유 사용자",
    )

    strategy_name: str = Field(
        max_length=100,
        nullable=False,
        description="전략 이름",
    )

    description: Optional[str] = Field(
        default=None,
        description="전략 설명",
    )

    rules: dict = Field(
        default_factory=dict,
        nullable=False,
        description="전략 룰 JSON",
        sa_column=Column(JSONB),
    )
