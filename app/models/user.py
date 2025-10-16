from typing import Optional
from sqlmodel import Field
from passlib.context import CryptContext
from app.models.base import BaseModel
from app.utils.security import get_password_hash, verify_password as _verify


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(BaseModel, table=True):
    """
    사용자 정보를 저장하는 테이블
    - JWT 인증 및 권한 관리 기반
    - 비밀번호는 bcrypt 해시로 저장
    """

    __tablename__ = "users"  # ✅ SQL 예약어 충돌 방지

    user_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="사용자 고유 ID",
        sa_column_kwargs={"autoincrement": True}
    )

    name: str = Field(
        max_length=50,
        nullable=False,
        description="사용자명 (표시용 이름)"
    )

    email: str = Field(
        max_length=100,
        nullable=False,
        description="이메일 (로그인용)",
        sa_column_kwargs={"unique": True}
    )

    password_hash: str = Field(
        max_length=255,
        nullable=False,
        description="bcrypt로 해시된 비밀번호"
    )

    is_active: bool = Field(
        default=True,
        description="계정 활성화 여부 (False 시 로그인 불가)"
    )

    role: str = Field(
        default="USER",
        max_length=20,
        description="권한 (USER, ADMIN 등)"
    )

    # -------------------- #
    # 비밀번호 관련 유틸리티
    # -------------------- #

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        비밀번호를 bcrypt로 해싱합니다.
        """
        return get_password_hash(password)

    def verify_password(self, password: str) -> bool:
        """
        입력한 비밀번호가 저장된 해시와 일치하는지 검증합니다.
        """
        return _verify(password, self.password_hash)

    # -------------------- #
    # 헬퍼 메서드
    # -------------------- #

    def to_dict(self) -> dict:
        """
        비밀번호 제외한 사용자 정보를 딕셔너리 형태로 반환합니다.
        """
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def __repr__(self) -> str:
        return f"<User(id={self.user_id}, name='{self.name}', email='{self.email}')>"
