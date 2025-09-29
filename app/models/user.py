import hashlib
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class User(BaseModel, table=True):
    """
    사용자 정보를 저장하는 테이블
    """
    __tablename__ = "user"

    id: int = Field(
        primary_key=True,
        description="사용자 ID",
        sa_column_kwargs={"autoincrement": True}
    )
    name: str = Field(max_length=50, description="사용자명")
    email: str = Field(max_length=100, description="이메일", unique=True)
    hashed_password: str = Field(max_length=255, description="해시된 비밀번호")

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        비밀번호를 해시화합니다.

        Args:
            password: 원본 비밀번호

        Returns:
            해시된 비밀번호
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        """
        비밀번호를 검증합니다.

        Args:
            password: 검증할 비밀번호

        Returns:
            비밀번호 일치 여부
        """
        return self.hashed_password == self.hash_password(password)

    def to_dict(self) -> dict:
        """
        User 객체를 딕셔너리로 변환합니다 (비밀번호 제외).

        Returns:
            사용자 정보 딕셔너리
        """
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}', email='{self.email}')>"
