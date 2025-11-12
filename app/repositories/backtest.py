from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date
from typing import Dict, Any

from app.models.backtest import BacktestResult

class BacktestRepository:
    async def create_backtest_result(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        ticker: str, # ticker는 아직 모델에 없지만, 추가를 고려해볼 수 있습니다.
        start_date: str,
        end_date: str,
        performance_data: Dict[str, Any]
    ) -> BacktestResult:
        """
        백테스팅 결과를 데이터베이스에 저장합니다.
        """
        
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()

        db_obj = BacktestResult(
            user_id=user_id,
            strategy_name=performance_data.get("strategy_name", "Unnamed Strategy"),
            start_date=start_date_obj,
            end_date=end_date_obj,
            total_return=performance_data.get("total_return", 0.0),
            win_rate=performance_data.get("win_rate", 0.0),
            max_drawdown=performance_data.get("max_drawdown", 0.0),
            total_trades=performance_data.get("total_trades", 0),
            final_portfolio_value=performance_data.get("final_portfolio_value", 0.0),
        )
        
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
