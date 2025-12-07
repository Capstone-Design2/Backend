# app/schemas/strategy.py
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrategyRequest(BaseModel):
    strategy_name: str = Field(description="전략 이름")
    description: str = Field(description="전략 설명")
    rules: Dict[str, Any] = Field(description="전략 룰 JSON")


class StrategyUpdateRequest(BaseModel):
    strategy_name: str = Field(description="전략 이름")
    description: str = Field(description="전략 설명")


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy_id: int = Field(description="전략 ID")
    strategy_name: str = Field(description="전략 이름")
    description: str = Field(description="전략 설명")
    rules: Dict[str, Any] = Field(description="전략 룰 JSON")


class StrategyChatRequest(BaseModel):
    session_id: Optional[str] = Field(default=None)  # 서버가 누구인지 알기 위한 id
    content: str = Field(description="메시지")

# 전략 상태 모델 (조건 충족 여부 + 상세 내용)


class ConditionDetail(BaseModel):
    filled: bool = False
    description: Optional[str] = None


class StrategyConditionState(BaseModel):
    indicators: ConditionDetail = Field(default_factory=ConditionDetail)
    buy_conditions: ConditionDetail = Field(default_factory=ConditionDetail)
    sell_conditions: ConditionDetail = Field(default_factory=ConditionDetail)
    trade_settings: ConditionDetail = Field(default_factory=ConditionDetail)
