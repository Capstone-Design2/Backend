from typing import Optional
from sqlmodel import Field
from sqlalchemy import UniqueConstraint
from app.models.base import BaseModel

class Tickers(BaseModel, table=True):
    """
    종목 정보를 저장하는 테이블
    """
    __tablename__ = "tickers"
    
    # 해외 주식과 병합할 경우를 대비해서 복합 유니크 구성
    __table_args__ = (
        UniqueConstraint("market", "symbol", name="unique_market_symbol"),
    )

    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="종목 ID",
        sa_column_kwargs={"autoincrement": True}
    )
    symbol: str = Field(max_length=20, description="종목 심볼", index=True)
    kis_code: str = Field(max_length=20, description="KIS 종목코드",unique=True)
    company_name: str = Field(max_length=100, description="기업명 또는 종목명")
    market: str = Field(max_length=20, description="거래소")
    currency: str = Field(max_length=4,default='KRW', description="거래 통화 단위")
    isin: str = Field(max_length=24, description="국제 증권 식별 코드",unique=True)

    def to_dict(self):
        """
        종목 정보 딕셔너리
        """
        return {
            "id": self.id,
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
        """
        디버깅이나 로깅할 때 필요한 정보있으면 추가하세여
        """
        return f"<Tickers(id={self.id}, symbol='{self.symbol}', company_name='{self.company_name}')>"