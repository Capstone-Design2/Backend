# app/routers/backtest.py
from fastapi import HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.backtest import (
    RunBacktestRequest,
    BacktestResultDetailSchema,
    BacktestJobSchema
)
from app.services.backtest import BacktestService
from app.repositories.backtest import BacktestRepository
from app.models.user import User
from app.models.backtest import BacktestStatus
from app.utils.dependencies import get_current_user
from app.utils.router import get_router

router = get_router("backtest")

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


@router.get("/results/{job_id}", response_model=BacktestResultDetailSchema)
async def get_backtest_result(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Job ID로 백테스트 결과를 조회합니다.
    """
    repo = BacktestRepository()
    result = await repo.get_backtest_result_by_job_id(db=db, job_id=job_id)

    if not result:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id}에 대한 백테스트 결과를 찾을 수 없습니다.")

    # 권한 확인 (본인의 결과만 조회 가능)
    if result.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="해당 백테스트 결과에 접근할 권한이 없습니다.")

    return result


@router.get("/results", response_model=List[BacktestResultDetailSchema])
async def get_user_backtest_results(
    limit: int = Query(10, ge=1, le=100, description="조회할 결과 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 결과 개수"),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    현재 사용자의 백테스트 결과 목록을 조회합니다.
    """
    repo = BacktestRepository()
    results = await repo.get_user_backtest_results(
        db=db,
        user_id=current_user.user_id,
        limit=limit,
        offset=offset
    )
    return results


@router.get("/jobs/{job_id}", response_model=BacktestJobSchema)
async def get_backtest_job(
    job_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Job ID로 백테스트 Job 정보를 조회합니다.
    """
    repo = BacktestRepository()
    job = await repo.get_backtest_job_by_id(db=db, job_id=job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id}를 찾을 수 없습니다.")

    # 권한 확인 (본인의 Job만 조회 가능)
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="해당 백테스트 Job에 접근할 권한이 없습니다.")

    return job


@router.get("/jobs", response_model=List[BacktestJobSchema])
async def get_user_backtest_jobs(
    status: Optional[BacktestStatus] = Query(None, description="필터링할 상태 (PENDING/RUNNING/COMPLETED/FAILED)"),
    limit: int = Query(10, ge=1, le=100, description="조회할 Job 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 Job 개수"),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    현재 사용자의 백테스트 Job 목록을 조회합니다.
    """
    repo = BacktestRepository()
    jobs = await repo.get_user_backtest_jobs(
        db=db,
        user_id=current_user.user_id,
        status=status,
        limit=limit,
        offset=offset
    )
    return jobs


@router.delete("/results/{result_id}", response_model=Dict[str, Any])
async def delete_backtest_result(
    result_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    백테스트 결과를 삭제합니다.
    """
    repo = BacktestRepository()

    # 결과 조회하여 권한 확인
    result = await repo.get_backtest_result_by_id(db=db, result_id=result_id)

    if not result:
        raise HTTPException(status_code=404, detail=f"Result ID {result_id}를 찾을 수 없습니다.")

    # 권한 확인 (본인의 결과만 삭제 가능)
    if result.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="해당 백테스트 결과를 삭제할 권한이 없습니다.")

    # 삭제 실행
    success = await repo.delete_backtest_result(db=db, result_id=result_id)

    if not success:
        raise HTTPException(status_code=500, detail="백테스트 결과 삭제에 실패했습니다.")

    return {"message": "백테스트 결과가 삭제되었습니다.", "result_id": result_id}
