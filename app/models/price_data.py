# app/models/price_data.py
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import Column, UniqueConstraint, CheckConstraint, BigInteger, String, text, Index
from sqlalchemy.types import Numeric, DateTime, Boolean
from sqlmodel import Field
from app.models.base import BaseModel


class PriceData(BaseModel, table=True):
    """
    시세(OHLCV) 시계열 데이터
    - (ticker_id, timestamp, timeframe, source) 유니크
    - timestamp는 UTC (timezone=True)
    """

    __tablename__ = "price_data"
    __table_args__ = (
        UniqueConstraint("ticker_id", "timestamp", "timeframe", "source",
                        name="uq_price_ticker_ts_tf_source"),
        CheckConstraint("timeframe IN ('1D','1h','30m','15m','5m','1m')",
                        name="ck_price_timeframe"),
        Index("ix_price_ticker_ts", "ticker_id", "timestamp"),
    )

    price_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="시세 레코드 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    ticker_id: int = Field(
        description="티커 ID(FK)"
    )

    timestamp: datetime = Field(
        description="UTC 타임스탬프",
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,                     
        ),
    )

    timeframe: str = Field(
        description="캔들 주기 (1D,1h,30m,15m,5m,1m)",
        sa_column=Column(String(3), nullable=False)
    )

    open: Optional[Decimal] = Field(
        description="시가",
        sa_column=Column(Numeric(20, 6), nullable=True)
    )
    high: Optional[Decimal] = Field(
        description="고가",
        sa_column=Column(Numeric(20, 6), nullable=True)
    )
    low: Optional[Decimal] = Field(
        description="저가",
        sa_column=Column(Numeric(20, 6), nullable=True)
    )
    close: Optional[Decimal] = Field(
        description="종가",
        sa_column=Column(Numeric(20, 6), nullable=True)
    )

    volume: Optional[int] = Field(
        description="거래량",
        sa_column=Column(BigInteger, nullable=True)
    )

    source: str = Field(
        default="KIS",
        description="데이터 출처",
        sa_column=Column(String(16), nullable=False, server_default=text("'KIS'"))
    )

    is_adjusted: bool = Field(
        default=False,
        description="배당/분할 반영 여부",
        sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
