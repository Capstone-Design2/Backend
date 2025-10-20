# app/routers/strategy.py
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.strategy import StrategyRequest
from app.schemas.user import UserResponse
from app.services.strategy import StrategyService
from app.utils.dependencies import get_current_user, get_strategy_service
from app.utils.router import get_router

router = get_router("strategy")


@router.post("/")
async def create_strategy(
    strategy_data: StrategyRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[StrategyService, Depends(get_strategy_service)],
):
    strategy = await service.create_strategy(strategy_data, db)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="전략 생성 실패")
    return strategy


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[StrategyService, Depends(get_strategy_service)],
):
    strategy = await service.get_strategy_by_id(strategy_id, db)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="전략 조회 실패")
    return strategy


@router.get("/")
async def get_user_strategies(
    db: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[StrategyService, Depends(get_strategy_service)],
    skip: int = 0,
    limit: int = 100,
):
    strategies = await service.get_all_strategies_by_user(skip, limit, db)
    if strategies is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="전략 조회 실패")
    return strategies


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    update_data: StrategyRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[StrategyService, Depends(get_strategy_service)],
):
    strategy = await service.update_strategy(strategy_id, update_data, db)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="전략 수정 실패")
    return strategy


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    db: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[StrategyService, Depends(get_strategy_service)],
):
    await service.delete_strategy(strategy_id, db)
    return {"message": "전략 삭제 성공"}
