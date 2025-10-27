# app/schemas/backtest.py
from datetime import date
from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    strategy_id: int = Field(..., description="전략 ID")
    ticker_id: int = Field(..., description="티커 ID")
    start_date: date = Field(..., description="시작일")
    end_date: date = Field(..., description="종료일")
