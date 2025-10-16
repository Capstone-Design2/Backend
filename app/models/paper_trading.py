from typing import Optional
from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel


class PaperTradingAccount(BaseModel, table=True):
    """
    모의투자 계좌 (사용자 1:1)
    """

    __tablename__ = "paper_trading_accounts"

    account_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="계좌 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    user_id: int = Field(
        foreign_key="users.user_id",
        nullable=False,
        description="소유 사용자",
    )

    initial_balance: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="초기 예수금",
    )

    current_balance: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="현재 현금 잔액",
    )

    total_asset_value: float = Field(
        sa_column=Column(Numeric(20, 8)),
        nullable=False,
        description="총 자산 평가액",
    )

    is_active: bool = Field(
        default=False,
        description="활성화 여부(Kill Switch)",
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_paper_account_user"),
    )
