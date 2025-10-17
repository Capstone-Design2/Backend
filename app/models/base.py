from datetime import datetime
from typing import Optional

from sqlalchemy.types import TIMESTAMP, Boolean
from sqlalchemy import func, text
from sqlmodel import SQLModel, Field
from pydantic import ConfigDict


class BaseModel(SQLModel):
    """
    모든 테이블에 공통으로 포함되는 기본 필드:
    - is_deleted: 소프트 삭제 여부
    - created_at: 생성 시각 (UTC)
    - updated_at: 수정 시각 (UTC)
    """
    __abstract__ = True  # 이 클래스로 테이블이 만들어지지 않도록

    # Pydantic v2: orm_mode → from_attributes
    model_config = ConfigDict(from_attributes=True)

    is_deleted: bool = Field(
        default=False,
        sa_type=Boolean,
        sa_column_kwargs={
            "nullable": False,
            "server_default": text("false"),
            "comment": "삭제 여부 (soft delete)",
        },
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=TIMESTAMP(timezone=True),
        sa_column_kwargs={
            "nullable": False,
            "server_default": func.now(),
            "comment": "레코드 생성일시 (UTC)",
        },
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        sa_type=TIMESTAMP(timezone=True),
        sa_column_kwargs={
            "nullable": True,
            "server_default": func.now(),
            "onupdate": func.now(),  # SQLAlchemy Column 인자도 column_kwargs로 전달 가능
            "comment": "레코드 수정일시 (UTC)",
        },
    )
