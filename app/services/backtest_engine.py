# app/services/backtest_engine.py
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, List, Any

class BacktestEngine:
    def __init__(self, strategy: Dict[str, Any], data: List[Dict[str, Any]]):
        self.strategy = strategy
        self.data = pd.DataFrame(data)
        self.results = {}
        self.initial_balance = 1000000

    def run(self) -> Dict[str, Any]:
        if len(self.data) < 2:
            return {"error": "Not enough data to run backtest"}
        self._calculate_indicators()
        self._execute_trades()
        self._calculate_metrics()
        return self.results

    def _calculate_indicators(self):
        if not hasattr(pd.DataFrame, 'ta'):
            pd.DataFrame.ta = ta.Exporter(self.data)
        
        for indicator in self.strategy.get('indicators', []):
            indicator_type = indicator.get('type')
            params = indicator.get('params', {})
            if hasattr(self.data.ta, indicator_type):
                getattr(self.data.ta, indicator_type)(**params, append=True)
        
        for derived in self.strategy.get('derived', []):
            formula = derived.get('formula')
            key = derived.get('key')
            if formula and key:
                try:
                    self.data[key] = self.data.eval(formula)
                except Exception as e:
                    print(f"Error calculating derived indicator {key}: {e}")

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
        self.data['equity'] = self.initial_balance
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
                self.data.loc[i, 'equity'] = self.data.loc[i-1, 'equity'] + self.data.loc[i-1, 'position'] * (self.data['close'][i] - self.data['close'][i-1])

        self.results['trades'] = trades

    def _calculate_metrics(self):
        if 'equity' not in self.data.columns or self.data['equity'].empty:
            self.results.update({'cagr': 0, 'sharpe': 0, 'max_drawdown': 0, 'equity_curve': []})
            return

        equity_curve = self.data['equity']
        total_return = (equity_curve.iloc[-1] / self.initial_balance) - 1
        num_years = (pd.to_datetime(self.data['timestamp'].iloc[-1]) - pd.to_datetime(self.data['timestamp'].iloc[0])).days / 365.25
        cagr = ((1 + total_return) ** (1 / num_years) - 1) if num_years > 0 else 0

        daily_returns = equity_curve.pct_change().dropna()
        sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0

        roll_max = equity_curve.cummax()
        daily_drawdown = equity_curve / roll_max - 1.0
        max_drawdown = daily_drawdown.min()

        self.results['cagr'] = cagr
        self.results['sharpe'] = sharpe
        self.results['max_drawdown'] = max_drawdown
        self.results['equity_curve'] = self.data[['timestamp', 'equity']].to_dict('records')