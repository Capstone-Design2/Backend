from pydantic import BaseModel, Field
from typing import List, Optional

from app.core.tradingview import SUPPORTED_RESOLUTIONS

class SymbolMetaOut(BaseModel):
    name: str
    ticker: str
    description: str
    exchange: str
    listed_exchange: str
    type: str
    session: str
    timezone: str
    minmov: int
    pricescale: int
    pointvalue: int = 1
    has_intraday: bool = True
    has_no_volume: bool = False
    supported_resolutions: List[str] = Field(default_factory=lambda: SUPPORTED_RESOLUTIONS)
    currency_code: str

class HistoryOut(BaseModel):
    s: str
    t: Optional[List[int]] = None
    o: Optional[List[float]] = None
    h: Optional[List[float]] = None
    l: Optional[List[float]] = None
    c: Optional[List[float]] = None
    v: Optional[List[int]] = None
    nextTime: Optional[int] = None
    
class SearchItemOut(BaseModel):
    symbol: str                
    full_name: str             
    description: str = ""      
    exchange: str = ""         
    ticker: str                
    type: str = "stock"
