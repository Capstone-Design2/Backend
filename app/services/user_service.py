import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.schemas import (
    ErrorResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)

logger = logging.getLogger(__name__)


class UserService:
    """
    사용자 관련 비즈니스 로직을 담당하는 Service 클래스
    """

    def __init__(self, user_repository: Optional[UserRepository] = None):
        self.user_repository = user_repository or UserRepository()

    async def create_user(
        self, db: AsyncSession, user_data: UserCreateRequest
    ) -> tuple[Optional[UserResponse], Optional[ErrorResponse]]:
        """
        새로운 사용자를 생성합니다.

        Args:
            db: 데이터베이스 세션
            user_data: 사용자 생성 요청 데이터 (name, email, password)

        Returns:
            성공 시: (UserResponse, None)
            실패 시: (None, ErrorResponse)
        """
        try:
            # 이메일 중복 확인
            if await self.user_repository.exists_by_email(db, user_data.email):
                error = ErrorResponse(
                    error="이미 존재하는 이메일입니다.",
                    detail=f"이메일 '{user_data.email}'은 이미 사용 중입니다.",
                )
                logger.warning(f"이메일 중복 생성 시도: {user_data.email}")
                return None, error

            # 사용자 생성 (password는 레포지토리에서 bcrypt 해시 처리)
            user = await self.user_repository.create(db, user_data.model_dump())
            if not user:
                error = ErrorResponse(
                    error="사용자 생성에 실패했습니다.",
                    detail="데이터베이스 오류가 발생했습니다.",
                )
                return None, error

            user_response = UserResponse.model_validate(user)
            logger.info(f"사용자 생성 서비스 완료: {user.email}")
            return user_response, None

        except Exception as e:
            error = ErrorResponse(
                error="사용자 생성 중 예외가 발생했습니다.",
                detail=str(e),
            )
            logger.error(f"사용자 생성 서비스 오류: {e}")
            return None, error

    async def get_user_by_id(
        self, db: AsyncSession, user_id: int
    ) -> tuple[Optional[UserResponse], Optional[ErrorResponse]]:
        """
        ID로 사용자를 조회합니다.
        """
        try:
            user = await self.user_repository.get_by_id(db, user_id)
            if not user:
                error = ErrorResponse(
                    error="사용자를 찾을 수 없습니다.",
                    detail=f"ID가 {user_id}인 사용자가 존재하지 않습니다.",
                )
                return None, error

            user_response = UserResponse.model_validate(user)
            logger.info(f"사용자 조회 서비스 완료: {user_id}")
            return user_response, None

        except Exception as e:
            error = ErrorResponse(
                error="사용자 조회 중 예외가 발생했습니다.",
                detail=str(e),
            )
            logger.error(f"사용자 조회 서비스 오류: {e}")
            return None, error

    async def get_all_users(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> tuple[Optional[UserListResponse], Optional[ErrorResponse]]:
        """
        모든 사용자를 조회합니다.
        """
        try:
            users = await self.user_repository.get_all(db, skip, limit)
            user_responses = [UserResponse.model_validate(user) for user in users]
            total = len(user_responses)

            user_list_response = UserListResponse(
                users=user_responses, total=total, skip=skip, limit=limit
            )

            logger.info(f"사용자 목록 조회 서비스 완료: {len(user_responses)}명")
            return user_list_response, None

        except Exception as e:
            error = ErrorResponse(
                error="사용자 목록 조회 중 예외가 발생했습니다.",
                detail=str(e),
            )
            logger.error(f"사용자 목록 조회 서비스 오류: {e}")
            return None, error

    async def update_user(
        self, db: AsyncSession, user_id: int, update_data: UserUpdateRequest
    ) -> tuple[Optional[UserResponse], Optional[ErrorResponse]]:
        """
        사용자 정보를 수정합니다.
        (update_data에 password가 포함되면 레포지토리에서 bcrypt 해시 처리)
        """
        try:
            update_dict = update_data.model_dump(exclude_unset=True)
            if not update_dict:
                error = ErrorResponse(
                    error="수정할 데이터가 없습니다.",
                    detail="최소 하나의 필드는 수정되어야 합니다.",
                )
                return None, error

            # 이메일 변경 시 중복 체크
            if "email" in update_dict:
                existing_user = await self.user_repository.get_by_email(
                    db, update_dict["email"]
                )
                if existing_user and existing_user.id != user_id:
                    error = ErrorResponse(
                        error="이미 존재하는 이메일입니다.",
                        detail=f"이메일 '{update_dict['email']}'은 이미 사용 중입니다.",
                    )
                    return None, error

            user = await self.user_repository.update(db, user_id, update_dict)
            if not user:
                error = ErrorResponse(
                    error="사용자를 찾을 수 없거나 수정에 실패했습니다.",
                    detail=f"ID가 {user_id}인 사용자의 정보를 수정할 수 없습니다.",
                )
                return None, error

            user_response = UserResponse.model_validate(user)
            logger.info(f"사용자 수정 서비스 완료: {user_id}")
            return user_response, None

        except Exception as e:
            error = ErrorResponse(
                error="사용자 정보 수정 중 예외가 발생했습니다.",
                detail=str(e),
            )
            logger.error(f"사용자 수정 서비스 오류: {e}")
            return None, error

    async def delete_user(self, db: AsyncSession, user_id: int) -> Optional[ErrorResponse]:
        """
        사용자를 삭제합니다.
        """
        try:
            success = await self.user_repository.delete(db, user_id)
            if not success:
                error = ErrorResponse(
                    error="사용자를 찾을 수 없거나 삭제에 실패했습니다.",
                    detail=f"ID가 {user_id}인 사용자를 삭제할 수 없습니다.",
                )
                return error

            logger.info(f"사용자 삭제 서비스 완료: {user_id}")
            return None

        except Exception as e:
            error = ErrorResponse(
                error="사용자 삭제 중 예외가 발생했습니다.",
                detail=str(e),
            )
            logger.error(f"사용자 삭제 서비스 오류: {e}")
            return error
