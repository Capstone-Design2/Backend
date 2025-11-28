# app/repositories/strategy.py
import logging
from typing import Any, Dict, List, Optional
from threading import Lock
import copy

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.strategy import Strategy

from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.strategy import StrategyConditionState

logger = logging.getLogger(__name__)


class StrategyRepository:
    """
    전략 데이터베이스 접근을 담당하는 Repository 클래스
    """

    async def create(self, data: Dict[str, Any], user_id: int, db: AsyncSession) -> Optional[Strategy]:
        """
        새로운 전략을 생성합니다.
        """
        try:
            strategy = Strategy(**data, user_id=user_id)
            db.add(strategy)
            await db.commit()
            await db.refresh(strategy)
            logger.info(
                f"Strategy created for user {user_id}: {strategy.strategy_name}")
            return strategy

        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating strategy for user {user_id}: {e}")
            return None

    async def get_by_id(self, strategy_id: int, db: AsyncSession) -> Optional[Strategy]:
        """
        ID로 특정 전략을 조회합니다.
        """
        try:
            result = await db.execute(select(Strategy).where(Strategy.strategy_id == strategy_id))
            strategy = result.scalars().first()
            if strategy is None:
                raise Exception(f"Strategy not found by id: {strategy_id}")
            return strategy
        except Exception as e:
            logger.error(f"Error getting strategy by id {strategy_id}: {e}")
            return None

    async def get_all_by_user_id(self, user_id: int, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Strategy]:
        """
        특정 사용자의 모든 전략을 조회합니다.
        """
        try:
            result = await db.execute(
                select(Strategy)
                .where(Strategy.user_id == user_id)
                .offset(skip)
                .limit(limit)
            )
            strategies = result.scalars().all()
            if len(strategies) == 0:
                raise Exception(f"No strategies found for user {user_id}")
            return strategies
        except Exception as e:
            raise Exception(
                f"Error getting all strategies for user {user_id}: {e}")

    async def update(self, strategy_id: int, update_data: Dict[str, Any], db: AsyncSession) -> Optional[Strategy]:
        """
        전략 정보를 수정합니다.
        """
        try:
            strategy = await self.get_by_id(strategy_id, db)
            if not strategy:
                raise Exception(
                    f"Strategy not found for update: {strategy_id}")

            for key, value in update_data.items():
                setattr(strategy, key, value)

            await db.commit()
            await db.refresh(strategy)
            return strategy

        except Exception as e:
            raise Exception(f"Error updating strategy {strategy_id}: {e}")

    async def delete(self, strategy_id: int, db: AsyncSession) -> bool:
        """
        전략을 삭제합니다.
        """
        try:
            strategy = await self.get_by_id(strategy_id, db)
            if not strategy:
                raise Exception(
                    f"Strategy not found for deletion: {strategy_id}")

            await db.delete(strategy)
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            raise Exception(f"Error deleting strategy {strategy_id}: {e}")
    

# 대화 상태 저장소 (state)
class StrategyStateRepository(ABC):
    @abstractmethod
    def get(self, session_id: str) -> StrategyConditionState:
        """세션상태 가져오기, 없으면 초기상태를 생성"""
        pass

    @abstractmethod
    def save(self, session_id: str, state: StrategyConditionState):
        """세션상태 저장"""
        pass

# In-memory 저장소 (전역 싱글톤)
class StrategyStateMemoryRepository(StrategyStateRepository):
    def __init__(self):
        self._states: Dict[str, StrategyConditionState] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> StrategyConditionState:
        """
        세션 상태를 가져오기,
        없으면 새 StrategyConditionState를 생성하여 저장 후 반환
        """
        with self._lock:
            if session_id not in self._states:
                # 초기 상태 자동 생성
                self._states[session_id] = StrategyConditionState()

            # 방어적 복사로 반환 (외부에서 값 변경 영향 방지)
            return copy.deepcopy(self._states[session_id])

    def save(self, session_id: str, state: StrategyConditionState):
        """
        세션상태 저장
        """
        with self._lock:
            self._states[session_id] = copy.deepcopy(state)

# 전역 인스턴스 (싱글톤)
_strategy_state_repo_singleton = StrategyStateMemoryRepository()

def get_strategy_state_repo() -> StrategyStateRepository:
    return _strategy_state_repo_singleton