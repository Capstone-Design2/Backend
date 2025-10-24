# app/cli/run_experiment.py
import argparse
import asyncio
import csv
import os
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.repositories.price import PriceRepository
from app.services.backtest import BacktestService
from app.services.strategy import StrategyService

async def main():
    parser = argparse.ArgumentParser(description="Run a backtest experiment.")
    parser.add_argument("--strategy-id", type=int, required=True, help="Strategy ID")
    parser.add_argument("--ticker-id", type=int, required=True, help="Ticker ID")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    async for db in get_session():
        strategy_service = StrategyService()
        strategy = await strategy_service.get_strategy_by_id(args.strategy_id, db)
        if not strategy:
            print(f"Strategy with id {args.strategy_id} not found.")
            return

        price_repository = PriceRepository()
        price_data = await price_repository.get_price_data(
            args.ticker_id, 
            datetime.strptime(args.start_date, "%Y-%m-%d").date(), 
            datetime.strptime(args.end_date, "%Y-%m-%d").date(), 
            db
        )

        if not price_data:
            print("No price data found for the given ticker and date range.")
            return

        # --- [핵심 수정] ---
        # BacktestService에 전달하기 전에 데이터를 DataFrame으로 만들고 타입을 변환합니다.
        price_data_dict = [p.model_dump() for p in price_data]
        df = pd.DataFrame(price_data_dict)
        
        price_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in price_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        # ------------------
        
        spec = strategy.rules  # ← DB에 저장된 전체 전략 dict
        backtest_service = BacktestService(spec, df)        
        results = backtest_service.run()

        if "error" in results:
            print(f"Backtest failed: {results['error']}")
            return

        # Save results
        if not os.path.exists('results'):
            os.makedirs('results')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"results/backtest_{args.strategy_id}_{args.ticker_id}_{timestamp}"

        # Save trades to CSV
        if results['trades']:  # 거래가 있을 경우에만 실행
            with open(f"{filename_base}_trades.csv", "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=results['trades'][0].keys())
                writer.writeheader()
                writer.writerows(results['trades'])
        else:  # 거래가 없을 경우 메시지 출력
            print("No trades were executed during the backtest.")

        # Save equity curve to CSV
        equity_df = pd.DataFrame(results['equity_curve'])
        equity_df.to_csv(f"{filename_base}_equity.csv", index=False)

        # Plot equity curve and save to PNG
        plt.figure(figsize=(12, 6))
        plt.plot(equity_df['timestamp'], equity_df['equity'])
        plt.title(f"Equity Curve for Strategy {args.strategy_id} on Ticker {args.ticker_id}")
        plt.xlabel("Date")
        plt.ylabel("Equity")
        plt.grid(True)
        plt.savefig(f"{filename_base}_equity.png")

        print(f"Backtest finished. Results saved to {filename_base}*")
        
        print("has dev.ema20?", 'dev.ema20' in df.columns, "min/max:", 
            df.get('dev.ema20').min() if 'dev.ema20' in df.columns else None, 
            df.get('dev.ema20').max() if 'dev.ema20' in df.columns else None)

        print("has bb.20.middle?", 'bb.20.middle' in df.columns, "NaN ratio:", 
            float(df['bb.20.middle'].isna().mean()) if 'bb.20.middle' in df.columns else None)
        
        k = results
        print(f"Trades: {len(k.get('trades', []))}")
        print({
            'CAGR(%)': round(float(k.get('cagr', 0))*100, 2),
            'Sharpe': round(float(k.get('sharpe', 0)), 2),
            'MDD(%)': round(float(k.get('max_drawdown', 0))*100, 2),
            'Calmar': round(float(k.get('calmar', 0)), 2),
        })

if __name__ == "__main__":
    asyncio.run(main())
