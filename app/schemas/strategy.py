# app/schemas/strategy.py
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class StrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="전략 이름")
    description: str = Field(..., description="전략 설명")
    rules: Dict[str, Any] = Field(..., description="전략 룰 JSON")


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: int = Field(..., description="전략 ID")
    strategy_name: str = Field(..., description="전략 이름")
    description: str = Field(..., description="전략 설명")
    rules: Dict[str, Any] = Field(..., description="전략 룰 JSON")
