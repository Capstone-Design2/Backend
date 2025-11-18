import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.user import User  # 경로 명확화

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
            user_data: 사용자 생성 데이터 (name, email, password)

        Returns:
            생성된 사용자 객체 또는 None
        """
        try:
            # 사전 중복 체크(선택)
            if await self.exists_by_email(db, user_data["email"]):
                logger.warning(f"이미 존재하는 이메일: {user_data['email']}")
                return None

            # 비밀번호 해시화 (bcrypt)
            password_hash = User.hash_password(user_data["password"])

            user = User(
                name=user_data["name"],
                email=user_data["email"],
                password_hash=password_hash,
            )

            db.add(user)
            await db.commit()
            await db.refresh(user)

            logger.info(f"사용자 생성 완료: {user.email}")
            return user

        except IntegrityError as ie:
            await db.rollback()
            logger.error(f"사용자 생성 무결성 오류 (email={user_data.get('email')}): {ie}")
            return None
        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 생성 오류: {e}")
            return None

    async def get_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        """
        ID로 사용자를 조회합니다.
        """
        try:
            result = await db.execute(select(User).where(User.user_id == user_id))
            user = result.scalars().first()

            if user:
                logger.info(f"사용자 ID 조회 완료: {user_id}")
            else:
                logger.warning(f"사용자 ID를 찾을 수 없음: {user_id}")

            return user

        except Exception as e:
            # 읽기 쿼리에서는 rollback이 필수는 아니지만 일관성 위해 유지
            await db.rollback()
            logger.error(f"사용자 ID 조회 오류 (user_id={user_id}): {e}")
            return None

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """
        이메일로 사용자를 조회합니다.
        """
        try:
            result = await db.execute(select(User).where(User.email == email))
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
        """
        try:
            result = await db.execute(select(User).offset(skip).limit(limit))
            users = result.scalars().all()

            logger.info(f"사용자 목록 조회 완료: {len(users)}명")
            return users

        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 목록 조회 오류: {e}")
            return []

    async def update(self, db: AsyncSession, user_id: int, update_data: dict) -> Optional[User]:
        """
        사용자 정보를 수정합니다.
        허용 필드: name, email, password -> password_hash로 변환 저장
        """
        try:
            user = await self.get_by_id(db, user_id)
            if not user:
                logger.warning(f"수정할 사용자를 찾을 수 없음: {user_id}")
                return None

            # password가 오면 bcrypt 해시로 변환
            if "password" in update_data and update_data["password"]:
                update_data["password_hash"] = User.hash_password(update_data.pop("password"))

            # 허용 필드만 업데이트
            allowed_fields = {"name", "email", "password_hash"}
            for key, value in update_data.items():
                if key in allowed_fields:
                    setattr(user, key, value)

            await db.commit()
            await db.refresh(user)

            logger.info(f"사용자 정보 수정 완료: {user_id}")
            return user

        except IntegrityError as ie:
            await db.rollback()
            logger.error(f"사용자 정보 수정 무결성 오류 (user_id={user_id}): {ie}")
            return None
        except Exception as e:
            await db.rollback()
            logger.error(f"사용자 정보 수정 오류 (user_id={user_id}): {e}")
            return None

    async def delete(self, db: AsyncSession, user_id: int) -> bool:
        """
        사용자를 삭제합니다.
        """
        try:
            user = await self.get_by_id(db, user_id)
            if not user:
                logger.warning(f"삭제할 사용자를 찾을 수 없음: {user_id}")
                return False

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
        """
        try:
            # User 객체를 로드하지 않고 email만 확인
            from sqlalchemy import func
            result = await db.execute(
                select(func.count()).select_from(User).where(User.email == email)
            )
            count = result.scalar()
            return count > 0

        except Exception as e:
            await db.rollback()
            logger.error(f"이메일 존재 여부 확인 오류 (email={email}): {e}")
            return False
