from __future__ import annotations
from typing import Dict, Optional
from pydantic import BaseModel, Field
from pydantic import ConfigDict

class TickerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker_id: int
    symbol: str
    kis_code: str | None = None
    company_name: str | None = None
    market: str | None = None
    currency: str
    isin: str | None = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class TickerSyncRequest(BaseModel):
    directory: Optional[str] = Field(
        default=None,
        example="/path/to/your/project/mnt/data",
        description="MST 파일들이 있는 디렉터리 경로 (기본: /mnt/data)",
    )

class TickerSyncResponse(BaseModel):
    total_synced: int
    per_market_counts: Dict[str, int]
    files_processed: int
    notes: Optional[str] = None
