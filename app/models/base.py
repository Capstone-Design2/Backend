from datetime import datetime
from typing import Optional

from sqlalchemy import Column, func
from sqlalchemy.types import TIMESTAMP, Boolean
from sqlmodel import SQLModel, Field


class BaseModel(SQLModel):
    """
    모든 테이블에 공통으로 포함되는 기본 필드:
    - is_deleted: 소프트 삭제 여부
    - created_at: 생성 시각 (UTC)
    - updated_at: 수정 시각 (UTC)
    """

    is_deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false", comment="삭제 여부")
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
            comment="레코드 생성일시 (UTC)"
        ),
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            TIMESTAMP(timezone=True),
            nullable=True,
            server_default=func.now(),
            onupdate=func.now(),
            comment="레코드 수정일시 (UTC)"
        ),
    )
