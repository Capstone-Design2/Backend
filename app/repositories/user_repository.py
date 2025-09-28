import logging
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    """
    사용자 데이터베이스 접근을 담당하는 Repository 클래스
    """

    async def create(self, db: AsyncSession, user_data: dict) -> Optional[User]:
        """
        새로운 사용자를 생성합니다.

        Args:
            db: 데이터베이스 세션
            user_data: 사용자 생성 데이터

        Returns:
            생성된 사용자 객체 또는 None
        """
        try:
            # 비밀번호 해시화
            hashed_password = User.hash_password(user_data["password"])

            # User 객체 생성
            user = User(
                name=user_data["name"],
                email=user_data["email"],
                hashed_password=hashed_password
            )

            # 데이터베이스에 추가
            db.add(user)
            await db.commit()
            await db.refresh(user)

            logger.info(f"사용자 생성 완료: {user.email}")
            return user

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 생성 오류: {e}")
            return None

    async def get_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        """
        ID로 사용자를 조회합니다.

        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID

        Returns:
            조회된 사용자 객체 또는 None
        """
        try:
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalars().first()

            if user:
                logger.info(f"사용자 ID 조회 완료: {user_id}")
            else:
                logger.warning(f"사용자 ID를 찾을 수 없음: {user_id}")

            return user

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 ID 조회 오류 (user_id={user_id}): {e}")
            return None

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """
        이메일로 사용자를 조회합니다.

        Args:
            db: 데이터베이스 세션
            email: 사용자 이메일

        Returns:
            조회된 사용자 객체 또는 None
        """
        try:
            result = await db.execute(
                select(User).where(User.email == email)
            )
            user = result.scalars().first()

            if user:
                logger.info(f"사용자 이메일 조회 완료: {email}")
            else:
                logger.warning(f"사용자 이메일을 찾을 수 없음: {email}")

            return user

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 이메일 조회 오류 (email={email}): {e}")
            return None

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        """
        모든 사용자를 조회합니다 (페이징 지원).

        Args:
            db: 데이터베이스 세션
            skip: 건너뛸 레코드 수
            limit: 조회할 최대 레코드 수

        Returns:
            사용자 리스트
        """
        try:
            result = await db.execute(
                select(User).offset(skip).limit(limit)
            )
            users = result.scalars().all()

            logger.info(f"사용자 목록 조회 완료: {len(users)}명")
            return list(users)

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 목록 조회 오류: {e}")
            return []

    async def update(self, db: AsyncSession, user_id: int, update_data: dict) -> Optional[User]:
        """
        사용자 정보를 수정합니다.

        Args:
            db: 데이터베이스 세션
            user_id: 수정할 사용자 ID
            update_data: 수정할 데이터

        Returns:
            수정된 사용자 객체 또는 None
        """
        try:
            # 기존 사용자 조회
            user = await self.get_by_id(db, user_id)
            if not user:
                logger.warning(f"수정할 사용자를 찾을 수 없음: {user_id}")
                return None

            # 비밀번호가 포함되어 있다면 해시화
            if "password" in update_data:
                update_data["hashed_password"] = User.hash_password(
                    update_data.pop("password"))

            # 사용자 정보 업데이트
            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            await db.commit()
            await db.refresh(user)

            logger.info(f"사용자 정보 수정 완료: {user_id}")
            return user

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 정보 수정 오류 (user_id={user_id}): {e}")
            return None

    async def delete(self, db: AsyncSession, user_id: int) -> bool:
        """
        사용자를 삭제합니다.

        Args:
            db: 데이터베이스 세션
            user_id: 삭제할 사용자 ID

        Returns:
            삭제 성공 여부
        """
        try:
            # 기존 사용자 조회
            user = await self.get_by_id(db, user_id)
            if not user:
                logger.warning(f"삭제할 사용자를 찾을 수 없음: {user_id}")
                return False

            # 사용자 삭제
            await db.delete(user)
            await db.commit()

            logger.info(f"사용자 삭제 완료: {user_id}")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 삭제 오류 (user_id={user_id}): {e}")
            return False

    async def exists_by_email(self, db: AsyncSession, email: str) -> bool:
        """
        이메일로 사용자 존재 여부를 확인합니다.

        Args:
            db: 데이터베이스 세션
            email: 확인할 이메일

        Returns:
            사용자 존재 여부
        """
        try:
            result = await db.execute(
                select(User.id).where(User.email == email)
            )
            exists = result.scalar() is not None

            logger.info(f"이메일 존재 여부 확인: {email} -> {exists}")
            return exists

        except Exception as e:
            await db.rollback()
            logger.error(f"이메일 존재 여부 확인 오류 (email={email}): {e}")
            return False
