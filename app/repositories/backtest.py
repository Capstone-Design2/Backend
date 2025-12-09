from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from decimal import Decimal

from app.models.backtest import BacktestJob, BacktestResult, BacktestStatus
from app.models.strategy import Strategy
from app.schemas.backtest import StrategyDefinitionSchema


class BacktestRepository:
    """백테스트 Job 및 Result 관리 Repository"""

    async def create_or_get_strategy(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        strategy_definition: StrategyDefinitionSchema
    ) -> Strategy:
        """
        전략 정의를 Strategy 테이블에 저장합니다.
        동일한 이름의 전략이 있으면 재사용하고, 없으면 새로 생성합니다.
        """
        strategy = Strategy(
            user_id=user_id,
            strategy_name=strategy_definition.strategy_name,
            description="Auto-generated from backtest request",
            rules=strategy_definition.model_dump()  # StrategyDefinitionSchema를 JSON으로 저장
        )

        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        return strategy

    async def create_backtest_job(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        strategy_id: int,
        ticker_id: int,
        start_date: date,
        end_date: date,
        timeframe: str = "1D"
    ) -> BacktestJob:
        """
        새로운 백테스트 Job을 생성합니다.
        """
        job = BacktestJob(
            user_id=user_id,
            strategy_id=strategy_id,
            ticker_id=ticker_id,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            status=BacktestStatus.PENDING
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def update_backtest_job_status(
        self,
        db: AsyncSession,
        job_id: int,
        status: BacktestStatus,
        completed_at: Optional[datetime] = None
    ) -> BacktestJob:
        """
        백테스트 Job의 상태를 업데이트합니다.
        """
        from sqlmodel import select

        stmt = select(BacktestJob).where(BacktestJob.job_id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"BacktestJob with id {job_id} not found")

        job.status = status
        if completed_at:
            job.completed_at = completed_at

        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def create_backtest_result(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        job_id: int,
        kpi: Dict[str, Any],
        equity_curve: List[Dict[str, Any]],
        max_drawdown: Optional[float] = None,
        cagr: Optional[float] = None,
        sharpe: Optional[float] = None
    ) -> BacktestResult:
        """
        백테스팅 결과를 데이터베이스에 저장합니다.
        성과 지표는 kpi JSONB 필드에 저장됩니다.
        """
        result = BacktestResult(
            user_id=user_id,
            job_id=job_id,
            cagr=Decimal(str(cagr)) if cagr is not None else None,
            sharpe=Decimal(str(sharpe)) if sharpe is not None else None,
            max_drawdown=Decimal(str(max_drawdown)) if max_drawdown is not None else None,
            kpi=kpi,
            equity_curve=equity_curve
        )

        db.add(result)
        await db.commit()
        await db.refresh(result)
        return result

    async def get_backtest_result_by_job_id(
        self,
        db: AsyncSession,
        job_id: int
    ) -> Optional[BacktestResult]:
        """
        Job ID로 백테스트 결과를 조회합니다.
        """
        from sqlmodel import select

        stmt = select(BacktestResult).where(BacktestResult.job_id == job_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_backtest_result_by_id(
        self,
        db: AsyncSession,
        result_id: int
    ) -> Optional[BacktestResult]:
        """
        Result ID로 백테스트 결과를 조회합니다.
        """
        from sqlmodel import select

        stmt = select(BacktestResult).where(BacktestResult.result_id == result_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_backtest_results(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[BacktestResult]:
        """
        사용자의 백테스트 결과 목록을 조회합니다.
        """
        from sqlmodel import select

        stmt = (
            select(BacktestResult)
            .where(BacktestResult.user_id == user_id)
            .order_by(BacktestResult.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_backtest_job_by_id(
        self,
        db: AsyncSession,
        job_id: int
    ) -> Optional[BacktestJob]:
        """
        Job ID로 백테스트 Job을 조회합니다.
        """
        from sqlmodel import select

        stmt = select(BacktestJob).where(BacktestJob.job_id == job_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_backtest_jobs(
        self,
        db: AsyncSession,
        user_id: int,
        status: Optional[BacktestStatus] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[BacktestJob]:
        """
        사용자의 백테스트 Job 목록을 조회합니다.
        """
        from sqlmodel import select

        stmt = select(BacktestJob).where(BacktestJob.user_id == user_id)

        if status:
            stmt = stmt.where(BacktestJob.status == status)

        stmt = stmt.order_by(BacktestJob.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def delete_backtest_result(
        self,
        db: AsyncSession,
        result_id: int
    ) -> bool:
        """
        백테스트 결과를 삭제합니다.
        """
        from sqlmodel import select

        stmt = select(BacktestResult).where(BacktestResult.result_id == result_id)
        result = await db.execute(stmt)
        backtest_result = result.scalar_one_or_none()

        if not backtest_result:
            return False

        await db.delete(backtest_result)
        await db.commit()
        return True
