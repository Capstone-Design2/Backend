from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreateRequest(BaseModel):
    """
    사용자 생성 요청 스키마
    """
    name: str = Field(..., min_length=1, max_length=50, description="사용자명")
    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(..., min_length=8, max_length=100,
                          description="비밀번호 (최소 8자)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "홍길동",
                "email": "hong@example.com",
                "password": "securepassword123"
            }
        }


class UserUpdateRequest(BaseModel):
    """
    사용자 정보 수정 요청 스키마
    """
    name: Optional[str] = Field(
        None, min_length=1, max_length=50, description="사용자명")
    email: Optional[EmailStr] = Field(None, description="이메일 주소")
    password: Optional[str] = Field(
        None, min_length=8, max_length=100, description="새 비밀번호")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "김철수",
                "email": "kim@example.com"
            }
        }


class UserResponse(BaseModel):
    """
    사용자 정보 응답 스키마
    """
    id: int = Field(..., description="사용자 ID")
    name: str = Field(..., description="사용자명")
    email: str = Field(..., description="이메일 주소")
    created_at: Optional[datetime] = Field(None, description="생성일시")
    updated_at: Optional[datetime] = Field(None, description="수정일시")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "홍길동",
                "email": "hong@example.com",
                "created_at": "2023-12-01T10:00:00",
                "updated_at": "2023-12-01T10:00:00"
            }
        }


class UserListResponse(BaseModel):
    """
    사용자 목록 응답 스키마
    """
    users: list[UserResponse] = Field(..., description="사용자 목록")
    total: int = Field(..., description="전체 사용자 수")
    skip: int = Field(..., description="건너뛴 레코드 수")
    limit: int = Field(..., description="조회한 레코드 수")

    class Config:
        json_schema_extra = {
            "example": {
                "users": [
                    {
                        "id": 1,
                        "name": "홍길동",
                        "email": "hong@example.com",
                        "created_at": "2023-12-01T10:00:00",
                        "updated_at": "2023-12-01T10:00:00"
                    }
                ],
                "total": 1,
                "skip": 0,
                "limit": 100
            }
        }


class ErrorResponse(BaseModel):
    """
    에러 응답 스키마
    """
    error: str = Field(..., description="에러 메시지")
    detail: Optional[str] = Field(None, description="상세 에러 정보")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "사용자를 찾을 수 없습니다.",
                "detail": "ID가 123인 사용자가 존재하지 않습니다."
            }
        }
