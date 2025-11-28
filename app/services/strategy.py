# app/services/strategy.py
import logging
from typing import List, Optional, Tuple

from app.repositories.strategy import StrategyRepository
from app.schemas.strategy import (StrategyChatRequest, StrategyRequest,
                                  StrategyResponse, StrategyUpdateRequest)
from app.schemas.user import UserResponse
from app.utils.llm_client import GeminiClient
from fastapi import HTTPException, status,Depends
from sqlalchemy.ext.asyncio import AsyncSession


from app.schemas.strategy import StrategyConditionState, StrategyChatRequest
from app.repositories.strategy import StrategyStateRepository
from app.repositories.strategy import get_strategy_state_repo
import uuid

logger = logging.getLogger(__name__)


class StrategyService:
    """
    전략 관련 비즈니스 로직을 담당하는 Service 클래스
    """

    def __init__(self, state_repo: StrategyStateRepository):
        self.strategy_repo = StrategyRepository()
        self.state_repo = state_repo

    async def create_strategy(
        self, strategy_data: StrategyRequest, db: AsyncSession, user_id: Optional[int] = 1
    ) -> Optional[StrategyResponse]:
        """
        새로운 전략을 생성합니다.
        """
        try:
            strategy = await self.strategy_repo.create(data=strategy_data.model_dump(), user_id=user_id, db=db)
            if not strategy:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="동일한 이름의 전략이 이미 존재할 수 있습니다.")

            strategy_response = StrategyResponse.model_validate(strategy)
            return strategy_response
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_strategy_by_id(
        self, strategy_id: int, db: AsyncSession, user_id: Optional[int] = 1
    ) -> Optional[StrategyResponse]:
        """
        ID로 특정 전략을 조회합니다. 사용자가 소유자인지 확인합니다.
        """
        try:
            strategy = await self.strategy_repo.get_by_id(strategy_id, db)
            if not strategy:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"ID {strategy_id}의 전략이 존재하지 않습니다.")

            if strategy.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="해당 전략에 접근할 권한이 없습니다.")

            strategy_response = StrategyResponse.model_validate(strategy)
            return strategy_response
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def get_all_strategies_by_user(
        self, skip: int, limit: int, db: AsyncSession, user_id: Optional[int] = 1
    ) -> Optional[List[StrategyResponse]]:
        """
        현재 사용자의 모든 전략 목록을 조회합니다.
        """
        try:
            strategies = await self.strategy_repo.get_all_by_user_id(user_id=user_id, db=db, skip=skip, limit=limit)
            # A more accurate count would query the DB without limit
            strategy_responses = [
                StrategyResponse.model_validate(s) for s in strategies]
            return strategy_responses
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def update_strategy(
        self, strategy_id: int, request: StrategyUpdateRequest, db: AsyncSession, user_id: Optional[int] = 1
    ) -> Optional[StrategyResponse]:
        try:
            strategy_to_update = await self.strategy_repo.get_by_id(strategy_id, db)
            if not strategy_to_update:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"ID {strategy_id}의 전략이 존재하지 않습니다.")

            if strategy_to_update.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="해당 전략을 수정할 권한이 없습니다.")

            update_dict = request.model_dump()

            updated_strategy = await self.strategy_repo.update(strategy_id, update_dict, db)
            if not updated_strategy:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="데이터베이스 오류 또는 중복된 이름일 수 있습니다.")

            strategy_response = StrategyResponse.model_validate(
                updated_strategy)
            return strategy_response
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def delete_strategy(
        self, strategy_id: int, db: AsyncSession, user_id: Optional[int] = 1
    ) -> Optional[StrategyResponse]:
        try:
            strategy_to_delete = await self.strategy_repo.get_by_id(strategy_id, db)
            if not strategy_to_delete:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"ID {strategy_id}의 전략이 존재하지 않습니다.")

            if strategy_to_delete.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="해당 전략을 삭제할 권한이 없습니다.")

            success = await self.strategy_repo.delete(strategy_id, db)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="데이터베이스에서 전략을 삭제하지 못했습니다.")

            return None
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    async def strategy_chat(self, request: StrategyChatRequest):
        session_id = request.session_id or str(uuid.uuid4())

        # 세션 상태 가져오기
        state = self.state_repo.get(session_id)

        # LLM 호출
        try:
            parsed = await GeminiClient.generate_strategy_chat(
                content=request.content,
                session_state=state.model_dump(),
            )
        except Exception as e:
            logger.error(f"Gemini 전략 채팅 중 오류 발생: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM 호출 중 오류가 발생했습니다: {e}",
            )

        # LLM 응답 기반으로 새로운 상태 구성
        new_state = StrategyConditionState(**parsed["conditions"])

        # 저장
        self.state_repo.save(session_id, new_state)
        status_value = parsed.get("status", "chat")

        return {
            "session_id": session_id,
            "status": status_value,
            "reply": parsed["reply"],
            "conditions": new_state.model_dump(),
            "strategy": parsed.get("strategy"),
        }