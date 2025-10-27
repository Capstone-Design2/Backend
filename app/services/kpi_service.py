# app/services/kpi_service.py
import pandas as pd
import numpy as np
from typing import Dict, List, Any

class KpiService:
    def __init__(self, equity_curve: pd.Series, trades: List[Dict[str, Any]], initial_balance: float):
        self.equity_curve = equity_curve
        self.trades = trades
        self.initial_balance = initial_balance

    def calculate_kpis(self) -> Dict[str, Any]:
        if self.equity_curve.empty:
            return {'cagr': 0, 'sharpe': 0, 'max_drawdown': 0}

        total_return = float((self.equity_curve.iloc[-1] / self.initial_balance) - 1)
        num_years = (self.equity_curve.index[-1] - self.equity_curve.index[0]).days / 365.25
        cagr = ((1 + total_return) ** (1 / num_years) - 1) if num_years > 0 else 0

        daily_returns = self.equity_curve.pct_change().dropna()
        sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0

        roll_max = self.equity_curve.cummax()
        daily_drawdown = self.equity_curve / roll_max - 1.0
        max_drawdown = daily_drawdown.min()

        return {
            'cagr': cagr,
            'sharpe': sharpe,
            'max_drawdown': max_drawdown,
        }
