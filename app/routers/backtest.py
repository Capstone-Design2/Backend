# app/routers/backtest.py
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.backtest import RunBacktestRequest
from app.services.backtest import BacktestService
from app.models.user import User
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/backtest",
    tags=["Backtest"],
)

@router.post("/run", response_model=Dict[str, Any])
async def run_backtest(
    req: RunBacktestRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    주어진 전략 정의에 따라 백테스팅을 실행하고 그 결과를 반환합니다.
    결과는 현재 로그인된 사용자의 정보와 함께 데이터베이스에 저장됩니다.
    """
    try:
        backtester = BacktestService(strategy_definition=req.strategy_definition, db=db)
        result = await backtester.run(
            ticker=req.ticker,
            start_date=str(req.start_date),
            end_date=str(req.end_date),
            user_id=current_user.user_id,
        )
        return result
    except Exception as e:
        # 운영 시 로깅 권장
        print(f"Backtest error: {e}")
        raise HTTPException(status_code=500, detail=f"백테스팅 중 오류가 발생했습니다: {e}")
