from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Numeric
from sqlmodel import Field
from app.models.base import BaseModel


class PriceData(BaseModel, table=True):
    """
    시세(OHLCV) 시계열 데이터
    - (ticker_id, timestamp, timeframe, source) 유니크 인덱스 권장
    - timestamp는 UTC
    """

    __tablename__ = "price_data"

    price_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="시세 레코드 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    ticker_id: int = Field(
        foreign_key="tickers.ticker_id",
        nullable=False,
        description="티커 ID",
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        description="캔들 시각(UTC)",
    )

    open: Optional[float] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8)),
        description="시가",
    )

    high: Optional[float] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8)),
        description="고가",
    )

    low: Optional[float] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8)),
        description="저가",
    )

    close: Optional[float] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8)),
        description="종가",
    )

    volume: Optional[int] = Field(
        default=None,
        description="거래량",
    )

    timeframe: str = Field(
        max_length=10,
        nullable=False,
        description="캔들 주기 (1D, 1h, 5m ...)",
    )

    source: str = Field(
        default="YFINANCE",
        max_length=20,
        description="수집 소스 (YFINANCE/KIS)",
    )

    is_adjusted: bool = Field(
        default=False,
        description="배당/분할 조정 여부",
    )


# SQLAlchemy-level index (optional but recommended)
Index(
    "uq_price_unique",
    PriceData.__table__.c.ticker_id,
    PriceData.__table__.c.timestamp,
    PriceData.__table__.c.timeframe,
    PriceData.__table__.c.source,
    unique=True,
)
