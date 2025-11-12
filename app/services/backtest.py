import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.repositories.backtest import BacktestRepository
from app.schemas.backtest import StrategyDefinitionSchema, ConditionGroupSchema, ConditionSchema, OperatorEnum
from app.utils.indicator_calculator import calculate_indicators
from app.repositories.ticker import TickerRepository
from app.repositories.price import PriceRepository


class BacktestService:
    def __init__(self, strategy_definition: StrategyDefinitionSchema, db: AsyncSession):
        self.strategy = strategy_definition
        self.db = db
        self.historical_data: Optional[pd.DataFrame] = None
        self.indicators_data: Dict[str, pd.Series | pd.DataFrame] = {}
        
        # Trading state
        self.trades: List[Dict] = []
        self.position: Optional[Dict] = None
        self.initial_cash = 10_000_000
        self.cash = self.initial_cash
        
        # For performance calculation
        self.portfolio_history: List[Dict] = []

    async def _load_data(self, ticker: str, start_date: str, end_date: str):
        """
        주어진 티커와 기간에 대한 과거 가격 데이터를 데이터베이스에서 로드합니다.
        """
        print(f"Loading data for {ticker} from {start_date} to {end_date}...")
        ticker_repo = TickerRepository()
        price_repo = PriceRepository()

        try:
            ticker_id = await ticker_repo.resolve_symbol_to_id(ticker, self.db)
        except ValueError as e:
            raise ValueError(f"Ticker '{ticker}' not found in database.") from e

        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()

        price_data_models = await price_repo.get_price_data(
            ticker_id=ticker_id,
            start_date=start_date_obj,
            end_date=end_date_obj,
            db=self.db
        )

        if not price_data_models:
            raise ValueError(f"No price data found for ticker '{ticker}' in the given date range.")

        # Convert list of Pydantic models to pandas DataFrame
        data = [
            {
                "timestamp": p.timestamp,
                "open": float(p.open),
                "high": float(p.high),
                "low": float(p.low),
                "close": float(p.close),
                "volume": p.volume,
            }
            for p in price_data_models
        ]
        
        df = pd.DataFrame(data)
        df = df.set_index("timestamp")
        
        self.historical_data = df
        print(f"Data loaded. {len(self.historical_data)} rows.")


    def _calculate_indicators(self):
        # ... (이전과 동일)
        print("Calculating indicators...")
        if self.historical_data is None:
            raise ValueError("Historical data is not loaded.")
        self.indicators_data = calculate_indicators(
            self.historical_data, self.strategy.indicators
        )
        print("Indicators calculated.")

    def _get_value(self, indicator_name: str, index: int) -> Optional[float]:
        """특정 시점(index)의 지표 값 또는 가격을 가져옵니다."""
        if self.historical_data is None: return None

        # 'price', 'close' 등 기본 가격 정보 처리
        if indicator_name.lower() in ['price', 'close', 'open', 'high', 'low']:
            return self.historical_data[indicator_name.lower()].iloc[index]

        # 복합 지표 처리 (e.g., "BBANDS.BBU_20_2.0")
        if '.' in indicator_name:
            main_indicator, column_name = indicator_name.split('.', 1)
            if main_indicator not in self.indicators_data:
                return None
            
            indicator_df = self.indicators_data[main_indicator]
            if isinstance(indicator_df, pd.DataFrame) and column_name in indicator_df.columns:
                try:
                    return indicator_df[column_name].iloc[index]
                except IndexError:
                    return None
            else:
                return None # DataFrame이 아니거나 컬럼이 존재하지 않음

        # 단일 지표 처리
        if indicator_name not in self.indicators_data:
            return None
        
        try:
            # Series인 경우
            return self.indicators_data[indicator_name].iloc[index]
        except (AttributeError, IndexError):
            return None

    def _check_single_condition(self, condition: ConditionSchema, index: int) -> bool:
        # ... (이전과 동일)
        if index == 0: return False
        val1_curr = self._get_value(condition.indicator1, index)
        val2_curr = self._get_value(condition.indicator2, index)
        if val1_curr is None or val2_curr is None: return False
        if condition.operator in [OperatorEnum.CROSSES_ABOVE, OperatorEnum.CROSSES_BELOW]:
            val1_prev = self._get_value(condition.indicator1, index - 1)
            val2_prev = self._get_value(condition.indicator2, index - 1)
            if val1_prev is None or val2_prev is None: return False
            if condition.operator == OperatorEnum.CROSSES_ABOVE: return val1_prev < val2_prev and val1_curr > val2_curr
            if condition.operator == OperatorEnum.CROSSES_BELOW: return val1_prev > val2_prev and val1_curr < val2_curr
        if condition.operator == OperatorEnum.IS_ABOVE: return val1_curr > val2_curr
        if condition.operator == OperatorEnum.IS_BELOW: return val1_curr < val2_curr
        return False

    def _check_condition_group(self, group: ConditionGroupSchema, index: int) -> bool:
        # ... (이전과 동일)
        if group.all: return all(self._check_single_condition(cond, index) for cond in group.all)
        if group.any: return any(self._check_single_condition(cond, index) for cond in group.any)
        return False

    def _evaluate_conditions(self, index: int) -> str:
        # ... (이전과 동일)
        if self.position is None:
            if self._check_condition_group(self.strategy.buy_conditions, index): return "buy"
        else:
            if self._check_condition_group(self.strategy.sell_conditions, index): return "sell"
        return "hold"

    def _execute_buy(self, index: int):
        # ... (이전과 동일)
        if self.historical_data is None: return
        price = self.historical_data['close'].iloc[index]
        date = self.historical_data.index[index]
        amount_to_invest = self.cash * (self.strategy.trade_settings.order_amount_percent / 100)
        quantity = amount_to_invest // price
        if quantity > 0:
            cost = quantity * price
            self.cash -= cost
            self.position = {'quantity': quantity, 'entry_price': price, 'entry_date': date}
            self.trades.append({'type': 'buy', 'date': date, 'price': price, 'quantity': quantity})
            print(f"[{date.date()}] BUY:  {quantity} shares at {price:,.0f} KRW")

    def _execute_sell(self, index: int):
        # ... (이전과 동일)
        if self.position is None or self.historical_data is None: return
        price = self.historical_data['close'].iloc[index]
        date = self.historical_data.index[index]
        quantity = self.position['quantity']
        sale_value = quantity * price
        self.cash += sale_value
        profit = (price - self.position['entry_price']) * quantity
        self.trades.append({'type': 'sell', 'date': date, 'price': price, 'quantity': quantity, 'profit': profit})
        print(f"[{date.date()}] SELL: {quantity} shares at {price:,.0f} KRW | Profit: {profit:,.0f} KRW")
        self.position = None

    def _update_portfolio_value(self, index: int):
        # ... (이전과 동일)
        if self.historical_data is None: return
        current_price = self.historical_data['close'].iloc[index]
        holdings_value = self.position['quantity'] * current_price if self.position else 0
        total_value = self.cash + holdings_value
        self.portfolio_history.append({'date': self.historical_data.index[index], 'value': total_value})

    def _calculate_performance_metrics(self) -> Dict[str, Any]:
        """시뮬레이션 결과를 바탕으로 최종 성과 지표를 계산합니다."""
        if not self.portfolio_history:
            return {"total_return": 0, "win_rate": 0, "max_drawdown": 0}

        # 1. 총수익률
        final_portfolio_value = self.portfolio_history[-1]['value']
        total_return = (final_portfolio_value - self.initial_cash) / self.initial_cash

        # 2. 승률
        sell_trades = [t for t in self.trades if t['type'] == 'sell']
        winning_trades = [t for t in sell_trades if t.get('profit', 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades) if sell_trades else 0

        # 3. 최대 낙폭 (MDD)
        portfolio_df = pd.DataFrame(self.portfolio_history).set_index('date')['value']
        peak = portfolio_df.cummax()
        drawdown = (portfolio_df - peak) / peak
        max_drawdown = drawdown.min() if not drawdown.empty else 0

        return {
            "total_return": total_return,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "final_portfolio_value": final_portfolio_value,
            "total_trades": len(sell_trades)
        }

    async def run(self, ticker: str, start_date: str, end_date: str, user_id: int) -> Dict:
        """백테스팅을 실행하고 결과를 DB에 저장합니다."""
        await self._load_data(ticker, start_date, end_date)
        self._calculate_indicators()

        self.cash = self.initial_cash
        self.position = None
        self.trades = []
        self.portfolio_history = []

        print("\nStarting simulation loop...")
        if self.historical_data is not None:
            for i in range(len(self.historical_data)):
                action = self._evaluate_conditions(i)
                if action == "buy": self._execute_buy(i)
                elif action == "sell": self._execute_sell(i)
                self._update_portfolio_value(i)
        print("Simulation finished.\n")
        
        performance = self._calculate_performance_metrics()
        
        # 결과를 DB에 저장
        try:
            repo = BacktestRepository()
            await repo.create_backtest_result(
                db=self.db,
                user_id=user_id,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                performance_data={**performance, "strategy_name": self.strategy.strategy_name}
            )
            print("Backtest results saved to database.")
        except Exception as e:
            print(f"Error saving backtest results: {e}")
            # DB 저장 실패가 전체 백테스팅 실패를 의미하지는 않으므로, 에러를 로깅하고 결과는 계속 반환합니다.

        return {"strategy_name": self.strategy.strategy_name, **performance}

# Example of how to run the service
if __name__ == '__main__':
    # 이 파일은 이제 DB 세션(AsyncSession)에 의존하므로, 직접 실행하기 어렵습니다.
    # FastAPI의 Depends()를 통해 주입받아야 하기 때문입니다.
    # 테스트를 위해서는 별도의 비동기 테스트 코드를 작성해야 합니다.
    print("This script cannot be run directly anymore due to DB dependency.")