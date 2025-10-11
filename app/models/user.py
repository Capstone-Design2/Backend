from typing import Optional
from sqlmodel import Field
from passlib.context import CryptContext
from app.models.base import BaseModel
from app.utils.security import get_password_hash, verify_password as _verify

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    password_hash: str = Field(max_length=255, description="bcrypt로 해시된 비밀번호")

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        비밀번호를 bcrypt로 해싱
        """
        return get_password_hash(password)

    def verify_password(self, password: str) -> bool:
        """
        입력한 비밀번호가 저장된 해시와 일치하는지 검증
        """
        return _verify(password, self.password_hash)

    def to_dict(self) -> dict:
        """
        비밀번호 제외한 사용자 정보 딕셔너리
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
