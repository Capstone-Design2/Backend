# routers/auth.py
from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas.auth import TokenPair, TokenRefreshRequest
from app.services.auth import AuthService
from app.utils.dependencies import get_current_user, get_auth_service
from app.utils.router import get_router
from app.models.user import User

router = get_router("auth")

# 폼 방식(OAuth2PasswordRequestForm) - Swagger Try it out에 잘 맞음
@router.post("/login", response_model=TokenPair)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(get_auth_service)],
):
    access, refresh = await service.login(
        email=form_data.username,
        password=form_data.password,
    )
    return TokenPair(access_token=access, refresh_token=refresh)

@router.post("/refresh", response_model=TokenPair)
async def refresh(
    req: TokenRefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
):
    access, refresh = await service.refresh(req.refresh_token)
    return TokenPair(access_token=access, refresh_token=refresh)

@router.get("/me")
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return {
        "id": current_user.user_id,
        "email": current_user.email,
        "name": current_user.name,
    }
