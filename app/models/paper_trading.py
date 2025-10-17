from typing import Optional
from decimal import Decimal
from sqlalchemy import Column, UniqueConstraint, CheckConstraint, text
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel


class PaperTradingAccount(BaseModel, table=True):
    """
    모의투자 계좌 (사용자 1:1)
    """

    __tablename__ = "paper_trading_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_paper_account_user"),
        # 음수 방지
        CheckConstraint("initial_balance >= 0", name="ck_pta_initial_balance_nonneg"),
        CheckConstraint("current_balance >= 0", name="ck_pta_current_balance_nonneg"),
        CheckConstraint("total_asset_value >= 0", name="ck_pta_total_asset_nonneg"),
    )

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

    initial_balance: Decimal = Field(
        default = Decimal("0"),
        sa_column=Column(Numeric(20, 8, asdecimal=True),server_default=text("0")),
        nullable=False,
        description="초기 예수금",
    )

    current_balance: Decimal = Field(
        default = Decimal("0"),
        sa_column=Column(Numeric(20, 8, asdecimal=True),server_default=text("0")),
        nullable=False,
        description="현재 현금 잔액",
    )

    total_asset_value: Decimal = Field(
        default = Decimal("0"),
        sa_column=Column(Numeric(20, 8, asdecimal=True),server_default=text("0")),
        nullable=False,
        description="총 자산 평가액",
    )

    is_active: bool = Field(
        default=False,
        description="활성화 여부(Kill Switch)",
        sa_column_kwargs={"server_default": text("0")}
    )
