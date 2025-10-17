from typing import Optional
from sqlmodel import Field
from sqlalchemy import UniqueConstraint
from app.models.base import BaseModel


class Ticker(BaseModel, table=True):
    """
    종목 메타 정보
    - KIS 코드/ISIN 포함
    """

    __tablename__ = "tickers"
    __table_args__ = (UniqueConstraint("market", "symbol", name="unique_market_symbol"),)


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
        index=True
    )

    kis_code: Optional[str] = Field(
        default=None,
        max_length=20,
        description="KIS 종목코드 (ex: 005930)",
        index=True
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
        max_length=4,
        description="거래 통화",
    )

    isin: Optional[str] = Field(
        default=None,
        max_length=24,
        description="국제 증권 식별 코드(ISIN)",
        unique=True
    )
    
    def to_dict(self) -> dict:
        return{
            "ticker_id": self.ticker_id,
            "symbol": self.symbol,
            "kis_code": self.kis_code,
            "company_name": self.company_name,
            "market": self.market,
            "currency": self.currency,
            "isin": self.isin,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def __repr__(self) -> str:
        return f"<Ticker(id={self.ticker_id}, symbol='{self.symbol}')>"