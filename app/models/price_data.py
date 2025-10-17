from datetime import datetime, timezone

from typing import Optional
from decimal import Decimal

from sqlalchemy import Column, Index, UniqueConstraint, CheckConstraint,text, BigInteger
from sqlalchemy import DateTime
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
    __table_args__ = (
        UniqueConstraint("ticker_id", "timestamp", "timeframe", "source",
                        name="uq_price_ticker_ts_tf_source"),
        CheckConstraint("timeframe IN ('1D','1h','30m','15m','5m','1m')",
                        name="ck_price_timeframe"),  
    )

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
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        description="캔들 시각(UTC)",
        sa_column=Column(DateTime(timezone=False)),
    )

    open: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        description="시가",
    )

    high: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        description="고가",
    )

    low: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        description="저가",
    )

    close: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(20, 8, asdecimal=True)),
        description="종가",
    )

    volume: Optional[int] = Field(
        default=None,
        description="거래량",
        sa_column=Column(BigInteger)
    )

    timeframe: str = Field(
        max_length=10,
        nullable=False,
        description="캔들 주기 (1D, 1h, 5m ...)",
    )

    source: str = Field(
        default="KIS",
        max_length=20,
        description="수집 소스 (YFINANCE/KIS)",
    )

    is_adjusted: bool = Field(
        default=False,
        description="배당/분할 조정 여부",
        sa_column_kwargs={"server_default": text("0")}
    )


# 조회 최적화용 인덱스
Index(
    "ix_price_ticker_tf_ts",
    PriceData.__table__.c.ticker_id,
    PriceData.__table__.c.timeframe,
    PriceData.__table__.c.timestamp,
)