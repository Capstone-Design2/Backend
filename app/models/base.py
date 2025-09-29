from datetime import datetime
from typing import Optional

from sqlalchemy import Column, func
from sqlalchemy.types import TIMESTAMP, Integer
from sqlmodel import Field, SQLModel


class BaseModel(SQLModel):
    """
    공통 생성/수정/삭제여부 필드를 포함하는 기본 모델
    모든 테이블에 is_deleted, created_at, updated_at 컬럼을 추가합니다.
    """
    # is_deleted: bool = Field(
    #     default=False, nullable=False, description="삭제 여부")

    created_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={
            "server_default": func.now(),
            "nullable": True,
            "comment": "레코드 생성일시"
        }
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "nullable": True,
            "comment": "레코드 수정일시"
        }
    )
