# app/services/backtest.py
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, List, Any
from app.services.kpi_service import KpiService

class BacktestService:
    def __init__(self, strategy: Dict[str, Any], data: List[Dict[str, Any]]):
        self.strategy = strategy
        self.data = pd.DataFrame(data)
        
        # --- [추가] 가격 관련 컬럼을 float으로 미리 변환 ---
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in self.data.columns:
                self.data[col] = pd.to_numeric(self.data[col])
        # --------------------------------------------------
        
        self.results = {}
        self.initial_balance = 1000000

    def run(self) -> Dict[str, Any]:
        # --- [디버깅용 print문 추가] ---
        print("--- Original Data Head ---")
        print(self.data.head()) # 데이터 시작 부분 확인
        print("--- Original Data Tail ---")
        print(self.data.tail()) # 데이터 끝 부분 확인
        
        if len(self.data) < 2:
            return {"error": "Not enough data to run backtest"}
        self._calculate_indicators()
        self._execute_trades()
        self._calculate_metrics()
        return self.results

    def _calculate_indicators(self):
        # strategy.json에 정의된 모든 지표를 계산합니다.
        for indicator in self.strategy.get('indicators', []):
            indicator_type = indicator.get('type')
            params = indicator.get('params', {})
            key = indicator.get('key')  # JSON에 정의된 key (e.g., "ema.20")

            try:
                # --- [핵심 수정] ---
                # ta.ema(), ta.bbands() 등 함수를 pandas_ta 라이브러리에서 직접 호출합니다.
                if indicator_type == 'ema':
                    # ta.ema(데이터, 파라미터) 형식으로 직접 호출
                    indicator_result = ta.ema(self.data['close'], **params)
                    # JSON에 정의된 key를 컬럼 이름으로 사용
                    self.data[key] = indicator_result

                elif indicator_type == 'bollinger_bands':
                    # pandas-ta는 볼린저 밴드를 'bbands'로 호출합니다.
                    indicator_result = ta.bbands(self.data['close'], **params)
                    
                    # 결과(DataFrame)의 컬럼 이름을 JSON 형식에 맞게 변경합니다.
                    # e.g., 'BBL_20_2.0' -> 'bb.20.lower'
                    rename_map = {
                        f'BBL_{params["length"]}_{params["stddev"]}': f'{key}.lower',
                        f'BBM_{params["length"]}_{params["stddev"]}': f'{key}.middle',
                        f'BBU_{params["length"]}_{params["stddev"]}': f'{key}.upper',
                        f'BBB_{params["length"]}_{params["stddev"]}': f'{key}.bandwidth',
                        f'BBP_{params["length"]}_{params["stddev"]}': f'{key}.percent',
                    }
                    indicator_result.rename(columns=rename_map, inplace=True)
                    
                    # 원래 데이터와 합칩니다.
                    self.data = pd.concat([self.data, indicator_result], axis=1)

            except Exception as e:
                print(f"지표 계산 중 오류 발생 ({indicator_type}): {e}")

        # 파생 지표 계산 (기존 로직 유지)
        for derived in self.strategy.get('derived', []):
            formula = derived.get('formula')
            key = derived.get('key')
            if formula and key:
                try:
                    self.data[key] = self.data.eval(formula)
                except Exception as e:
                    print(f"파생 지표 계산 중 오류 ({key}): {e}")

        # --- [디버깅용 print문] ---
        # 이제 EMA 컬럼이 정상적으로 생성되었는지 확인합니다.
        print("\n--- All Column Names (After Calculation) ---")
        print(self.data.columns)
        # ---------------------------

    def _evaluate_condition(self, condition: Dict[str, Any], i: int) -> bool:
        cond_type = condition.get('type')
        if cond_type == 'compare':
            lhs_key = condition['lhs']
            rhs_key = condition['rhs']
            if lhs_key not in self.data.columns or rhs_key not in self.data.columns:
                return False
            lhs = self.data[lhs_key][i]
            rhs = self.data[rhs_key][i]
            op = condition['op']
            ops = {'<=': lambda a, b: a <= b, '>=': lambda a, b: a >= b, '<': lambda a, b: a < b, '>': lambda a, b: a > b}
            if op in ops:
                return ops[op](lhs, rhs)
        elif cond_type == 'crosses_above':
            lhs_key = condition['lhs']
            rhs_key = condition['rhs']
            if lhs_key not in self.data.columns or rhs_key not in self.data.columns:
                return False
            
            # --- [디버깅용 print문 추가] ---
            # i가 특정 값일 때 (예: 마지막 날) 값들을 출력해봅니다.
            if i == len(self.data) - 1: 
                print(f"\n--- Evaluating 'crosses_above' at index {i} ---")
                print(f"Yesterday: {lhs_key}[{i-1}] = {self.data[lhs_key][i-1]}, {rhs_key}[{i-1}] = {self.data[rhs_key][i-1]}")
                print(f"Today:     {lhs_key}[{i}] = {self.data[lhs_key][i]}, {rhs_key}[{i}] = {self.data[rhs_key][i]}")
            # -----------------------------
            
            return self.data[lhs_key][i-1] < self.data[rhs_key][i-1] and self.data[lhs_key][i] > self.data[rhs_key][i]
        elif cond_type == 'crosses_below':
            lhs_key = condition['lhs']
            rhs_key = condition['rhs']
            if lhs_key not in self.data.columns or rhs_key not in self.data.columns:
                return False
            return self.data[lhs_key][i-1] > self.data[rhs_key][i-1] and self.data[lhs_key][i] < self.data[rhs_key][i]
        elif cond_type == 'touched_within':
            within = condition['within']
            sub_condition = condition['condition']
            for j in range(max(0, i - within), i + 1):
                if self._evaluate_condition(sub_condition, j):
                    return True
            return False
        elif cond_type == 'threshold':
            lhs_key = condition['lhs']
            if lhs_key not in self.data.columns:
                return False
            lhs = self.data[lhs_key][i]
            value = condition['value']
            op = condition['op']
            ops = {'<=': lambda a, b: a <= b, '>=': lambda a, b: a >= b, '<': lambda a, b: a < b, '>': lambda a, b: a > b}
            if op in ops:
                return ops[op](lhs, value)
        return False

    def _execute_trades(self):
        self.data['signal'] = 0
        self.data['position'] = 0
        self.data['equity'] = float(self.initial_balance)
        trades = []
        position = 0

        for i in range(1, len(self.data)):
            if position == 0:
                if all(self._evaluate_condition(cond, i) for cond in self.strategy.get('rules', {}).get('buy_condition', {}).get('entry', [])):
                    self.data.loc[i, 'signal'] = 1
                    position = 1
                    trades.append({'timestamp': self.data['timestamp'][i], 'price': self.data['close'][i], 'side': 'buy'})
                elif all(self._evaluate_condition(cond, i) for cond in self.strategy.get('rules', {}).get('sell_condition', {}).get('entry', [])):
                    self.data.loc[i, 'signal'] = -1
                    position = -1
                    trades.append({'timestamp': self.data['timestamp'][i], 'price': self.data['close'][i], 'side': 'sell'})
            elif position == 1:
                if any(self._evaluate_condition(cond, i) for cond in self.strategy.get('rules', {}).get('buy_condition', {}).get('exit', [])):
                    self.data.loc[i, 'signal'] = -1
                    position = 0
                    trades.append({'timestamp': self.data['timestamp'][i], 'price': self.data['close'][i], 'side': 'sell'})
            elif position == -1:
                if any(self._evaluate_condition(cond, i) for cond in self.strategy.get('rules', {}).get('sell_condition', {}).get('exit', [])):
                    self.data.loc[i, 'signal'] = 1
                    position = 0
                    trades.append({'timestamp': self.data['timestamp'][i], 'price': self.data['close'][i], 'side': 'buy'})
            
            self.data.loc[i, 'position'] = position
            if i > 0:
                # 가격 변화를 float으로 계산
                price_change = float(self.data['close'][i]) - float(self.data['close'][i-1])
                # float 타입으로 통일하여 최종 equity 계산
                self.data.loc[i, 'equity'] = self.data.loc[i-1, 'equity'] + self.data.loc[i-1, 'position'] * price_change

        self.results['trades'] = trades
        self.results['equity_curve'] = self.data[['timestamp', 'equity']].to_dict('records')

    def _calculate_metrics(self):
        kpi_service = KpiService(
            pd.Series([item['equity'] for item in self.results['equity_curve']], 
                      index=pd.to_datetime([item['timestamp'] for item in self.results['equity_curve']])),
            self.results['trades'], 
            self.initial_balance
        )
        kpis = kpi_service.calculate_kpis()
        self.results.update(kpis)
