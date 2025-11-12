from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import List, Dict, Any, Optional
from enum import Enum

class OperatorEnum(str, Enum):
    """
    조건에 사용될 연산자를 정의하는 Enum
    """
    IS_ABOVE = "is_above"
    IS_BELOW = "is_below"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class IndicatorSchema(BaseModel):
    """
    개별 기술 지표를 정의하는 스키마
    - name: 전략 내에서 이 지표를 식별하는 고유한 이름 (e.g., 'SMA_short')
    - type: 지표의 종류 (e.g., 'SMA', 'EMA', 'BBANDS')
    - params: 지표 계산에 필요한 파라미터 (e.g., {'period': 20})
    """
    name: str = Field(description="전략 내 지표의 고유 이름")
    type: str = Field(description="지표 종류 (e.g., 'SMA', 'RSI')")
    params: Dict[str, Any] = Field(description="지표 계산 파라미터")


class ConditionSchema(BaseModel):
    """
    매수/매도 조건을 정의하는 스키마
    - indicator1: 비교할 첫 번째 지표 (e.g., 'SMA_short', 'price')
    - operator: 비교 연산자
    - indicator2: 비교할 두 번째 지표 (e.g., 'SMA_long', 'bbands_upper')
    """
    indicator1: str = Field(description="비교할 첫 번째 지표 이름 또는 'price'")
    operator: OperatorEnum = Field(description="비교 연산자")
    indicator2: str = Field(description="비교할 두 번째 지표 이름 또는 상수값")


class ConditionGroupSchema(BaseModel):
    """
    여러 조건을 AND/OR로 묶는 그룹
    - all: 리스트 안의 모든 조건이 참이어야 함 (AND)
    - any: 리스트 안의 조건 중 하나라도 참이면 됨 (OR)
    """
    all: Optional[List[ConditionSchema]] = None
    any: Optional[List[ConditionSchema]] = None

    @model_validator(mode="after")
    def _xor_all_any(self):
        has_all = bool(self.all)
        has_any = bool(self.any)
        if has_all and has_any:
            raise ValueError("Cannot have both 'all' and 'any' conditions in the same group.")
        if not has_all and not has_any:
            raise ValueError("Either 'all' or 'any' must be provided.")
        return self


class TradeSettingsSchema(BaseModel):
    """
    거래 실행에 대한 설정을 정의하는 스키마
    """
    order_amount_percent: float = Field(
        100.0,
        gt=0,
        le=100,
        description="주문 시 사용할 자산의 비율(%)"
    )


class StrategyDefinitionSchema(BaseModel):
    """
    사용자 정의 전략의 전체 구조를 정의하는 최상위 스키마
    LLM이 최종적으로 생성해야 할 JSON 포맷입니다.
    """
    strategy_name: str = Field(description="전략의 이름")
    indicators: List[IndicatorSchema] = Field(description="전략에 사용될 지표 목록")
    buy_conditions: ConditionGroupSchema = Field(description="매수 조건 그룹")
    sell_conditions: ConditionGroupSchema = Field(description="매도 조건 그룹")
    trade_settings: TradeSettingsSchema = Field(description="거래 설정")
    
    # Pydantic v2 ORM 설정
    model_config = ConfigDict(from_attributes=True)


class BacktestResultSchema(BaseModel):
    """백테스팅 실행 결과"""
    job_id: int = Field(description="백테스트 Job ID")
    strategy_name: str = Field(description="전략 이름")
    total_return: float = Field(description="총 수익률")
    win_rate: float = Field(description="승률")
    max_drawdown: float = Field(description="최대 낙폭")
    cagr: float = Field(description="연평균 복리 수익률 (CAGR)")
    sharpe_ratio: float = Field(description="샤프 지수")
    completed_trades: int = Field(description="완료된 거래 수 (라운드 트립)")
    buy_count: int = Field(description="매수 액션 수")
    sell_count: int = Field(description="매도 액션 수")
    total_actions: int = Field(description="총 액션 수 (매수 + 매도)")
    final_portfolio_value: float = Field(description="최종 포트폴리오 가치")

    # ✅ v2 방식: orm_mode 대체
    model_config = ConfigDict(from_attributes=True)


class BacktestResultDetailSchema(BaseModel):
    """백테스팅 결과 상세 정보 (DB에서 조회)"""
    result_id: int = Field(description="결과 ID")
    job_id: int = Field(description="백테스트 Job ID")
    user_id: int = Field(description="사용자 ID")
    max_drawdown: Optional[float] = Field(None, description="최대 낙폭")
    cagr: Optional[float] = Field(None, description="연평균 복리 수익률")
    sharpe: Optional[float] = Field(None, description="샤프 지수")
    kpi: Dict[str, Any] = Field(description="성과 지표 (JSON)")
    equity_curve: List[Dict[str, Any]] = Field(description="자산 곡선 (JSON)")
    created_at: datetime = Field(description="생성 시각")

    # ✅ v2 방식: orm_mode 대체
    model_config = ConfigDict(from_attributes=True)


class BacktestJobSchema(BaseModel):
    """백테스트 Job 정보"""
    job_id: int = Field(description="Job ID")
    user_id: int = Field(description="사용자 ID")
    strategy_id: int = Field(description="전략 ID")
    ticker_id: int = Field(description="티커 ID")
    start_date: date = Field(description="시작일")
    end_date: date = Field(description="종료일")
    timeframe: str = Field(description="타임프레임")
    status: str = Field(description="상태 (PENDING/RUNNING/COMPLETED/FAILED)")
    completed_at: Optional[datetime] = Field(None, description="완료 시각")
    created_at: datetime = Field(description="생성 시각")

    # ✅ v2 방식: orm_mode 대체
    model_config = ConfigDict(from_attributes=True)
    
class RunBacktestRequest(BaseModel):
    ticker: str = Field(description="백테스팅을 실행할 티커 (e.g., '005930')")
    start_date: date = Field(description="시작일 (YYYY-MM-DD)")
    end_date: date = Field(description="종료일 (YYYY-MM-DD)")
    strategy_definition: StrategyDefinitionSchema = Field(description="LLM이 생성한 전략 정의 JSON")

    # ✅ Pydantic v2 설정 + Swagger 예제 고정(각 그룹은 all/any 중 하나만)
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "ticker": "005930",
                "start_date": "2023-01-01",
                "end_date": "2024-12-31",
                "strategy_definition": {
                    "strategy_name": "SMA Cross Demo",
                    "indicators": [
                        {"name": "sma20", "type": "SMA", "params": {"length": 20}},
                        {"name": "sma60", "type": "SMA", "params": {"length": 60}}
                    ],
                    "buy_conditions": {
                        "all": [
                            {"indicator1": "sma20", "operator": "crosses_above", "indicator2": "sma60"}
                        ]
                    },
                    "sell_conditions": {
                        "any": [
                            {"indicator1": "sma20", "operator": "crosses_below", "indicator2": "sma60"}
                        ]
                    },
                    "trade_settings": {"order_amount_percent": 100.0}
                }
            }
        }
    )