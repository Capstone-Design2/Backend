from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm

from app.database import get_session as get_db
from app.schemas.auth_schema import TokenPair, TokenRefreshRequest
from app.services.auth_service import AuthService
from app.utils.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# (A) 폼 방식(OAuth2PasswordRequestForm) - Swagger Try it out에 잘 맞음
@router.post("/login", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    svc = AuthService(db)
    access, refresh = await svc.login(
        email=form_data.username,
        password=form_data.password,
    )
    return TokenPair(access_token=access, refresh_token=refresh)

# (B) JSON 바디 방식이 편하면 아래를 사용 (주석 해제해서 A 대신 사용 가능)
# from app.schemas.auth_schema import LoginRequest
# @router.post("/login", response_model=TokenPair)
# async def login_json(req: LoginRequest, db: AsyncSession = Depends(get_db)):
#     svc = AuthService(db)
#     access, refresh = await svc.login(email=req.email, password=req.password)
#     return TokenPair(access_token=access, refresh_token=refresh)

@router.post("/refresh", response_model=TokenPair)
async def refresh(req: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    access, refresh = await svc.refresh(req.refresh_token)
    return TokenPair(access_token=access, refresh_token=refresh)

@router.get("/me")
async def me(current_user = Depends(get_current_user)):
    # 모델에 role 필드가 없다면 반환하지 않습니다.
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
    }
