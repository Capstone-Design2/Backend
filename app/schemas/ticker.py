from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


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


class TickerSyncResponse(BaseModel):
    total_synced: int
    per_market_counts: Dict[str, int]
    files_processed: int
    notes: Optional[str] = None
