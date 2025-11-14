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
        print(f"✓ Loaded {len(self.historical_data)} price records ({start_date} ~ {end_date})")


    def _calculate_indicators(self):
        if self.historical_data is None:
            raise ValueError("Historical data is not loaded.")

        # Suppress pandas-ta verbose output
        import sys
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()  # Redirect stdout to suppress output

        try:
            self.indicators_data = calculate_indicators(
                self.historical_data, self.strategy.indicators
            )
        finally:
            sys.stdout = old_stdout  # Restore stdout

        print(f"✓ Indicators calculated: {', '.join(self.indicators_data.keys())}")

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
            cash_before = self.cash
            self.cash -= cost
            self.position = {'quantity': quantity, 'entry_price': price, 'entry_date': date}
            self.trades.append({'type': 'buy', 'date': date, 'price': price, 'quantity': quantity})
            print(f"  [{date.date()}] BUY  {int(quantity):>4} shares @ {price:>8,.0f} KRW | Cash: {cash_before:>12,.0f} → {self.cash:>12,.0f}")

    def _execute_sell(self, index: int):
        # ... (이전과 동일)
        if self.position is None or self.historical_data is None: return
        price = self.historical_data['close'].iloc[index]
        date = self.historical_data.index[index]
        quantity = self.position['quantity']
        sale_value = quantity * price
        cash_before = self.cash
        self.cash += sale_value
        profit = (price - self.position['entry_price']) * quantity
        self.trades.append({'type': 'sell', 'date': date, 'price': price, 'quantity': quantity, 'profit': profit})
        profit_sign = "+" if profit >= 0 else ""
        print(f"  [{date.date()}] SELL {int(quantity):>4} shares @ {price:>8,.0f} KRW | P&L: {profit_sign}{profit:>10,.0f} | Cash: {cash_before:>12,.0f} → {self.cash:>12,.0f}")
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
            return {
                "total_return": 0,
                "win_rate": 0,
                "max_drawdown": 0,
                "cagr": 0,
                "sharpe_ratio": 0,
                "final_portfolio_value": self.initial_cash,
                "completed_trades": 0,
                "buy_count": 0,
                "sell_count": 0,
                "total_actions": 0
            }

        # 1. 총수익률
        final_portfolio_value = self.portfolio_history[-1]['value']
        total_return = (final_portfolio_value - self.initial_cash) / self.initial_cash

        # 2. 거래 카운트
        buy_trades = [t for t in self.trades if t['type'] == 'buy']
        sell_trades = [t for t in self.trades if t['type'] == 'sell']
        buy_count = len(buy_trades)
        sell_count = len(sell_trades)
        total_actions = buy_count + sell_count
        completed_trades = sell_count  # 완료된 라운드 트립

        # 3. 승률
        winning_trades = [t for t in sell_trades if t.get('profit', 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades) if sell_trades else 0

        # 4. 최대 낙폭 (MDD)
        portfolio_df = pd.DataFrame(self.portfolio_history).set_index('date')['value']
        peak = portfolio_df.cummax()
        drawdown = (portfolio_df - peak) / peak
        max_drawdown = drawdown.min() if not drawdown.empty else 0

        # 5. CAGR (Compound Annual Growth Rate)
        if len(self.portfolio_history) > 1:
            start_date = self.portfolio_history[0]['date']
            end_date = self.portfolio_history[-1]['date']
            days = (end_date - start_date).days
            years = days / 365.25

            if years > 0:
                cagr = (final_portfolio_value / self.initial_cash) ** (1 / years) - 1
            else:
                cagr = 0
        else:
            cagr = 0

        # 6. Sharpe Ratio (일간 수익률 기준)
        if len(self.portfolio_history) > 1:
            # 일간 수익률 계산
            daily_returns = portfolio_df.pct_change().dropna()

            if len(daily_returns) > 0:
                # 평균 일간 수익률
                mean_daily_return = daily_returns.mean()
                # 일간 수익률 표준편차
                std_daily_return = daily_returns.std()

                if std_daily_return > 0:
                    # 연율화된 Sharpe Ratio (무위험 수익률 0으로 가정)
                    # 252 거래일 기준
                    sharpe_ratio = (mean_daily_return / std_daily_return) * np.sqrt(252)
                else:
                    sharpe_ratio = 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        return {
            "total_return": total_return,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "cagr": cagr,
            "sharpe_ratio": sharpe_ratio,
            "final_portfolio_value": final_portfolio_value,
            "completed_trades": completed_trades,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "total_actions": total_actions
        }

    async def run(self, ticker: str, start_date: str, end_date: str, user_id: int) -> Dict:
        """백테스팅을 실행하고 결과를 DB에 저장합니다."""
        repo = BacktestRepository()
        ticker_repo = TickerRepository()
        job_id = None

        try:
            # 1. Ticker ID 조회
            ticker_id = await ticker_repo.resolve_symbol_to_id(ticker, self.db)

            # 2. Strategy 생성 (또는 재사용)
            strategy = await repo.create_or_get_strategy(
                db=self.db,
                user_id=user_id,
                strategy_definition=self.strategy
            )

            # 3. BacktestJob 생성
            from datetime import datetime
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()

            job = await repo.create_backtest_job(
                db=self.db,
                user_id=user_id,
                strategy_id=strategy.strategy_id,
                ticker_id=ticker_id,
                start_date=start_date_obj,
                end_date=end_date_obj,
                timeframe="1D"
            )
            job_id = job.job_id
            print(f"\n{'='*80}")
            print(f"BACKTEST JOB #{job_id} | Strategy: {self.strategy.strategy_name}")
            print(f"Initial Capital: {self.initial_cash:,.0f} KRW")
            print(f"{'='*80}")

            # 4. Job 상태를 RUNNING으로 변경
            from app.models.backtest import BacktestStatus
            await repo.update_backtest_job_status(
                db=self.db,
                job_id=job_id,
                status=BacktestStatus.RUNNING
            )

            # 5. 데이터 로드 및 시뮬레이션 실행
            await self._load_data(ticker, start_date, end_date)
            self._calculate_indicators()

            self.cash = self.initial_cash
            self.position = None
            self.trades = []
            self.portfolio_history = []

            print("✓ Starting simulation...")
            buy_signal_count = 0
            sell_signal_count = 0

            if self.historical_data is not None:
                for i in range(len(self.historical_data)):
                    action = self._evaluate_conditions(i)

                    if action == "buy":
                        buy_signal_count += 1
                        self._execute_buy(i)
                    elif action == "sell":
                        sell_signal_count += 1
                        self._execute_sell(i)
                    self._update_portfolio_value(i)

            print(f"✓ Simulation completed: {buy_signal_count} buys, {sell_signal_count} sells")

            # 6. 성과 지표 계산
            performance = self._calculate_performance_metrics()

            # 7. Equity curve 데이터 준비 (포트폴리오 히스토리를 JSON 형식으로)
            equity_curve = [
                {
                    "timestamp": item['date'].isoformat(),
                    "value": float(item['value'])
                }
                for item in self.portfolio_history
            ]

            # 8. KPI 데이터 준비 (추가 지표들)
            kpi = {
                "strategy_name": self.strategy.strategy_name,
                "total_return": performance['total_return'],
                "win_rate": performance['win_rate'],
                "completed_trades": performance['completed_trades'],
                "buy_count": performance['buy_count'],
                "sell_count": performance['sell_count'],
                "total_actions": performance['total_actions'],
                "final_portfolio_value": performance['final_portfolio_value'],
                "initial_cash": self.initial_cash,
                "cagr": performance['cagr'],
                "sharpe_ratio": performance['sharpe_ratio'],
                "trades": [
                    {
                        "type": t['type'],
                        "date": t['date'].isoformat(),
                        "price": float(t['price']),
                        "quantity": float(t['quantity']),
                        "profit": float(t.get('profit', 0))
                    }
                    for t in self.trades
                ]
            }

            # 9. 결과 저장
            await repo.create_backtest_result(
                db=self.db,
                user_id=user_id,
                job_id=job_id,
                kpi=kpi,
                equity_curve=equity_curve,
                max_drawdown=performance['max_drawdown'],
                cagr=performance['cagr'],
                sharpe=performance['sharpe_ratio']
            )

            # 10. Job 상태를 COMPLETED로 변경
            from datetime import timezone
            await repo.update_backtest_job_status(
                db=self.db,
                job_id=job_id,
                status=BacktestStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )

            # 최종 현금 및 포지션 정보
            final_cash = self.cash
            final_position_value = 0
            if self.position and self.historical_data is not None:
                final_price = self.historical_data['close'].iloc[-1]
                final_position_value = self.position['quantity'] * final_price

            print(f"\n{'─'*80}")
            print(f"FINAL SUMMARY")
            print(f"{'─'*80}")
            print(f"  Initial Capital    : {self.initial_cash:>15,.0f} KRW")
            print(f"  Final Cash         : {final_cash:>15,.0f} KRW")
            if final_position_value > 0:
                print(f"  Position Value     : {final_position_value:>15,.0f} KRW ({int(self.position['quantity'])} shares)")
            print(f"  Total Portfolio    : {performance['final_portfolio_value']:>15,.0f} KRW")
            print(f"  {'─'*78}")
            print(f"  Total Return       : {performance['total_return']:>14.2%}")
            print(f"  CAGR               : {performance['cagr']:>14.2%}")
            print(f"  Sharpe Ratio       : {performance['sharpe_ratio']:>14.2f}")
            print(f"  Max Drawdown       : {performance['max_drawdown']:>14.2%}")
            print(f"  Win Rate           : {performance['win_rate']:>14.2%}")
            print(f"  {'─'*78}")
            print(f"  Buy Actions        : {performance['buy_count']:>14}")
            print(f"  Sell Actions       : {performance['sell_count']:>14}")
            print(f"  Total Actions      : {performance['total_actions']:>14}")
            print(f"  Completed Trades   : {performance['completed_trades']:>14}")
            print(f"{'='*80}\n")

        except Exception as e:
            print(f"\n[ERROR] Backtest failed: {e}")
            # Job이 생성된 경우 상태를 FAILED로 변경
            if job_id:
                try:
                    await repo.update_backtest_job_status(
                        db=self.db,
                        job_id=job_id,
                        status=BacktestStatus.FAILED
                    )
                except Exception as update_error:
                    print(f"Error updating job status to FAILED: {update_error}")
            raise  # 원래 에러를 다시 발생시켜 API 레벨에서 처리하도록 함

        return {
            "job_id": job_id,
            "strategy_name": self.strategy.strategy_name,
            **performance
        }

# Example of how to run the service
if __name__ == '__main__':
    # 이 파일은 이제 DB 세션(AsyncSession)에 의존하므로, 직접 실행하기 어렵습니다.
    # FastAPI의 Depends()를 통해 주입받아야 하기 때문입니다.
    # 테스트를 위해서는 별도의 비동기 테스트 코드를 작성해야 합니다.
    print("This script cannot be run directly anymore due to DB dependency.")