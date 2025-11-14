from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import Column,CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import DateTime
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel

from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from datetime import date, datetime

if TYPE_CHECKING:
    # 순환 import 방지용(런타임 import 아님)
    from app.models.user import User

class BacktestStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BacktestJob(BaseModel, table=True):
    """
    백테스트 실행 요청/상태
    """

    __tablename__ = "backtest_jobs"
    __table_args__ = ( CheckConstraint("start_date <= end_date", name="ck_btjob_date_range"), 
        # 자주 쓰는 필터에 맞춰 인덱스(선택) 
        # Index("ix_btjob_user_status", "user_id", "status"), 
    )

    job_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="백테스트 잡 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    user_id: int = Field(
        foreign_key="users.user_id",
        nullable=False,
        description="요청 사용자",
    )

    strategy_id: int = Field(
        foreign_key="strategies.strategy_id",
        nullable=False,
        description="사용 전략",
    )

    ticker_id: int = Field(
        foreign_key="tickers.ticker_id",
        nullable=False,
        description="대상 티커",
    )

    start_date: date = Field(
        nullable=False,
        description="시작 일자",
    )

    end_date: date = Field(
        nullable=False,
        description="종료 일자",
    )

    timeframe: str = Field(
        default="1D",
        max_length=10,
        description="캔들 주기",
    )

    status: BacktestStatus = Field(
        default=BacktestStatus.PENDING,
        description="잡 상태",
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        description="완료 시각(UTC)",
        sa_column=Column(DateTime(timezone=False), nullable=True),
    )


class BacktestResult(BaseModel, table=True):
    """
    백테스트 결과 요약
    - KPI & equity_curve 는 JSON 보관
    """

    __tablename__ = "backtest_results"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_btres_job"),
    )
    
    user_id: int = Field(
        foreign_key="users.user_id",
        nullable=False,
        description="소유 사용자",
    )
    user: "User" = Relationship(back_populates="backtest_results")

    result_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="백테스트 결과 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    job_id: int = Field(
        foreign_key="backtest_jobs.job_id",
        nullable=False,
        description="원천 잡 ID",
    )

    cagr: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 6, asdecimal=True)),
        description="연평균 수익률",
    )

    sharpe: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 6, asdecimal=True)),
        description="샤프지수",
    )

    max_drawdown: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 6, asdecimal=True)),
        description="최대 낙폭",
    )

    kpi: dict = Field(
        default_factory=dict,
        description="기타 성과지표(JSON)",
        sa_column=Column(JSONB, nullable=False),
    )

    equity_curve: list = Field(
        default_factory=list,
        description="자산 곡선 (list of {ts, equity})",
        sa_column=Column(JSONB, nullable=False),
    )
