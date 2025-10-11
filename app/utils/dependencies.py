# utils/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.utils.security import decode_token

# Swagger에서 Authorize → 토큰만 입력해도 Bearer 자동으로 붙음
auth_scheme = HTTPBearer()

def get_user_service() -> UserService:
    """
    사용자 서비스 의존성 주입 (FastAPI Depends용)
    """
    return UserService()

async def get_auth_service(db: AsyncSession = Depends(get_session)) -> AuthService:
    """
    AuthService 의존성 주입용 팩토리 함수.
    """
    return AuthService(db)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db: AsyncSession = Depends(get_session),
):
    """
    JWT Access Token을 해독하고 현재 로그인한 사용자 반환
    """
    token = credentials.credentials  # <-- "Bearer xxx"에서 xxx 추출
    payload = decode_token(token)
    
    if not payload or payload.get("scope") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or expired token"
        )

    email = payload.get("sub")
    repo = UserRepository()
    user = await repo.get_by_email(db, email)
    
    if not user:
        raise HTTPException(
            status_code=401, 
            detail="User not found"
        )
        
    return user