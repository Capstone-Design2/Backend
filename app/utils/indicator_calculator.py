import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Any
from app.schemas.backtest import IndicatorSchema

def calculate_indicators(
    historical_data: pd.DataFrame,
    indicator_definitions: List[IndicatorSchema]
) -> Dict[str, pd.Series]:
    """
    전략 정의에 명시된 모든 기술 지표를 계산합니다.

    Args:
        historical_data (pd.DataFrame): 'open', 'high', 'low', 'close', 'volume' 컬럼을 포함하는 OHLCV 데이터
        indicator_definitions (List[IndicatorSchema]): 계산할 지표의 정의 목록

    Returns:
        Dict[str, pd.Series]: 지표의 고유 이름(name)을 키로, 계산된 Series를 값으로 하는 딕셔너리
    """
    if historical_data.empty:
        return {}

    # pandas-ta는 컬럼 이름이 소문자일 것을 기대합니다.
    data = historical_data.copy()
    data.columns = [col.lower() for col in data.columns]

    calculated_indicators = {}

    for indicator_def in indicator_definitions:
        indicator_type = indicator_def.type.lower()
        indicator_params = indicator_def.params.copy()
        
        # pandas-ta의 지표 함수를 동적으로 가져옵니다.
        # 예: indicator_type이 'sma'이면 df.ta.sma() 함수를 찾습니다.
        indicator_func = getattr(data.ta, indicator_type, None)

        if indicator_func is None:
            print(f"Warning: Indicator type '{indicator_def.type}' not found in pandas_ta. Skipping.")
            continue

        try:
            # 지표 계산 실행
            # 예: data.ta.sma(length=20, append=False)
            result = indicator_func(**indicator_params, append=False)

            # 결과가 여러 컬럼(e.g., 볼린저밴드)을 포함하는 DataFrame일 수 있습니다.
            if isinstance(result, pd.DataFrame):
                # 컬럼 이름이 'BB_UPPER_20_2.0', 'BB_LOWER_20_2.0' 등으로 생성됩니다.
                # 스키마에 정의된 고유 이름으로 접근할 수 있도록 매핑이 필요할 수 있으나,
                # 우선은 계산된 그대로 저장하고, 조건 평가 단계에서 컬럼 이름을 조합하여 사용합니다.
                calculated_indicators[indicator_def.name] = result
            else: # 대부분의 경우 결과는 Series 입니다.
                calculated_indicators[indicator_def.name] = result

        except Exception as e:
            print(f"[ERROR] Failed to calculate indicator '{indicator_def.name}': {e}")

    return calculated_indicators

if __name__ == '__main__':
    # --- 테스트용 코드 ---
    # 가상의 가격 데이터 생성
    dates = pd.date_range(start='2023-01-01', periods=50, freq='D')
    dummy_data = pd.DataFrame({
        'open': pd.np.random.uniform(90, 110, 50),
        'high': pd.np.random.uniform(100, 120, 50),
        'low': pd.np.random.uniform(80, 100, 50),
        'close': pd.np.random.uniform(95, 115, 50),
        'volume': pd.np.random.uniform(1000, 5000, 50),
    }, index=dates)

    # MA Crossover 전략에 필요한 지표 정의
    indicators_to_calc = [
        IndicatorSchema(name="SMA_short", type="SMA", params={"length": 5}),
        IndicatorSchema(name="SMA_long", type="SMA", params={"length": 20}),
        IndicatorSchema(name="RSI", type="RSI", params={"length": 14}),
        IndicatorSchema(
            name="BBANDS", 
            type="BBANDS", 
            params={"length": 20, "std": 2}
        ),
    ]

    # 지표 계산 함수 실행
    indicator_results = calculate_indicators(dummy_data, indicators_to_calc)

    # 결과 확인
    print("--- Calculated Indicators ---")
    for name, series in indicator_results.items():
        print(f"\nIndicator: {name}")
        # 볼린저밴드처럼 여러 컬럼을 반환하는 경우 DataFrame으로 출력됨
        print(series.tail())
