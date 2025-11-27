# utils/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.kis_auth import KISAuthManager, get_kis_auth_manager
from app.services.price import PriceService
from app.services.strategy import StrategyService
from app.services.ticker import TickerService
from app.services.user import UserService
from app.utils.security import decode_token

from app.repositories.strategy import StrategyStateRepository, get_strategy_state_repo
from app.repositories.strategy import StrategyStateMemoryRepository


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

    sub = payload.get("sub")
    # ★ 타입 내로잉: str 타입인지 검증해서 None/Unknown 제거
    if not isinstance(sub, str) or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload (sub)",
        )
    email: str = sub

    repo = UserRepository()
    user = await repo.get_by_email(db, email)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_ticker_service(
    auth_manager: KISAuthManager = Depends(get_kis_auth_manager),
) -> TickerService:
    return TickerService(auth_manager=auth_manager)


def get_strategy_service(
    state_repo: StrategyStateRepository = Depends(get_strategy_state_repo),
):
    return StrategyService(state_repo=state_repo)


async def get_price_service() -> PriceService:
    return PriceService()


