# routers/user.py
from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import (
    ErrorResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.user import UserService
from app.utils.router import get_router
from app.utils.dependencies import get_user_service
from app.utils.dependencies import get_current_user  # ✅ JWT 인증용 의존성 추가

# 라우터 생성
router = get_router("user")


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 생성",
    description="새로운 사용자를 생성합니다 (회원가입).",
    responses={
        201: {"model": UserResponse, "description": "사용자 생성 성공"},
        400: {"model": ErrorResponse, "description": "이미 존재하는 이메일 또는 잘못된 데이터"},
    },
)
async def create_user(
    user_data: UserCreateRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """
    새로운 사용자를 생성합니다.

    - **name**: 사용자명 (1-50자)
    - **email**: 이메일 주소 (유효한 이메일 형식)
    - **password**: 비밀번호 (최소 8자)
    """
    user_response, error = await service.create_user(db, user_data)

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.model_dump(),
        )

    return user_response


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 조회",
    description="ID로 특정 사용자를 조회합니다 (JWT 필요).",
    responses={
        200: {"model": UserResponse, "description": "사용자 조회 성공"},
        401: {"description": "인증 실패 또는 토큰 없음"},
        404: {"model": ErrorResponse, "description": "사용자를 찾을 수 없음"},
    },
)
async def get_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],  # ✅ 인증된 사용자만 접근 가능
):
    """
    ID로 특정 사용자를 조회합니다.
    JWT 인증이 필요합니다.

    - **user_id**: 조회할 사용자의 ID
    """
    user_response, error = await service.get_user_by_id(db, user_id)

    if error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error.model_dump(),
        )

    return user_response


@router.get(
    "/",
    response_model=UserListResponse,
    summary="사용자 목록 조회",
    description="모든 사용자의 목록을 조회합니다 (관리자 전용, JWT 필요).",
    responses={
        200: {"model": UserListResponse, "description": "사용자 목록 조회 성공"},
        401: {"description": "인증 실패 또는 토큰 없음"},
    },
)
async def get_users(
    service: Annotated[UserService, Depends(get_user_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],  # ✅ 보호된 엔드포인트
    skip: int = 0,
    limit: int = 100,
):
    """
    모든 사용자의 목록을 조회합니다 (JWT 필요).

    - **skip**: 건너뛸 레코드 수 (기본값: 0)
    - **limit**: 조회할 최대 레코드 수 (기본값: 100)
    """
    user_list_response, error = await service.get_all_users(db, skip, limit)

    if error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error.model_dump(),
        )

    return user_list_response


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 정보 수정",
    description="특정 사용자의 정보를 수정합니다 (JWT 필요).",
    responses={
        200: {"model": UserResponse, "description": "사용자 정보 수정 성공"},
        400: {"model": ErrorResponse, "description": "잘못된 데이터 또는 이미 존재하는 이메일"},
        401: {"description": "인증 실패 또는 토큰 없음"},
        404: {"model": ErrorResponse, "description": "사용자를 찾을 수 없음"},
    },
)
async def update_user(
    user_id: int,
    update_data: UserUpdateRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],  # ✅ JWT 필요
):
    """
    특정 사용자의 정보를 수정합니다 (JWT 필요).

    - **user_id**: 수정할 사용자의 ID
    - **name**: 새로운 사용자명 (선택사항)
    - **email**: 새로운 이메일 주소 (선택사항)
    - **password**: 새로운 비밀번호 (선택사항)
    """
    user_response, error = await service.update_user(db, user_id, update_data)

    if error:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "찾을 수 없" in error.error
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=error.model_dump(),
        )

    return user_response


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="사용자 삭제",
    description="특정 사용자를 삭제합니다 (JWT 필요).",
    responses={
        204: {"description": "사용자 삭제 성공"},
        401: {"description": "인증 실패 또는 토큰 없음"},
        404: {"model": ErrorResponse, "description": "사용자를 찾을 수 없음"},
    },
)
async def delete_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],  # ✅ JWT 필요
):
    """
    특정 사용자를 삭제합니다 (JWT 필요).

    - **user_id**: 삭제할 사용자의 ID
    """
    error = await service.delete_user(db, user_id)

    if error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error.model_dump(),
        )

    return None
