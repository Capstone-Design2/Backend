# services/auth_service.py
import logging
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.utils.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.models.user import User

logger = logging.getLogger(__name__)


class AuthService:
    """
    JWT 기반 인증 로직 담당
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository()

    async def login(self, email: str, password: str) -> tuple[str, str]:
        """
        로그인 처리 및 JWT 토큰 발급
        """
        user: User | None = await self.user_repo.get_by_email(self.db, email)
        if not user:
            logger.warning(f"Login failed: user not found ({email})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # ✅ password_hash 사용
        if not verify_password(password, user.password_hash):
            logger.warning(f"Login failed: invalid password ({email})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # ✅ security.py 시그니처에 맞게 호출 (sub, role)
        access_token = create_access_token(sub=user.email, role="user")
        refresh_token = create_refresh_token(sub=user.email)

        logger.info(f"User login success: {user.email}")
        return access_token, refresh_token

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        """
        Refresh Token을 검증하고 새로운 Access/Refresh Token 발급
        """
        from app.utils.security import decode_token

        payload = decode_token(refresh_token)
        if not payload or payload.get("scope") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        email = payload.get("sub")
        user = await self.user_repo.get_by_email(self.db, email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        new_access = create_access_token(sub=user.email, role="user")
        new_refresh = create_refresh_token(sub=user.email)

        logger.info(f"Token refreshed for {user.email}")
        return new_access, new_refresh
