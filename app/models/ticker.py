from typing import Optional
from sqlmodel import Field
from app.models.base import BaseModel


class Ticker(BaseModel, table=True):
    """
    종목 메타 정보
    - KIS 코드/ISIN 포함
    """

    __tablename__ = "tickers"

    ticker_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="티커 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    symbol: str = Field(
        max_length=20,
        nullable=False,
        description="심볼 (ex: 005930.KS, AAPL)",
        sa_column_kwargs={"unique": True},
    )

    kis_code: Optional[str] = Field(
        default=None,
        max_length=20,
        description="KIS 종목코드 (ex: 005930)",
    )

    company_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="기업/종목명",
    )

    market: Optional[str] = Field(
        default=None,
        max_length=20,
        description="시장 (KOSPI/NASDAQ/ETF 등)",
    )

    currency: str = Field(
        default="KRW",
        max_length=10,
        description="거래 통화",
    )

    isin: Optional[str] = Field(
        default=None,
        max_length=24,
        description="국제 증권 식별 코드(ISIN)",
    )
