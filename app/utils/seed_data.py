# app/utils/seed_data.py
"""
초기 데이터 시딩 유틸리티
다른 환경에서도 기본 전략 데이터가 자동으로 생성되도록 합니다.
"""
import json
import logging
from pathlib import Path
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.strategy import Strategy
from app.models.user import User

logger = logging.getLogger(__name__)


# 기본 전략 템플릿 정의
_strategies_cache = None


def load_strategies_from_json() -> List[dict]:
    """JSON 파일에서 전략 리스트를 로드합니다. (Lazy loading with cache)"""
    global _strategies_cache

    if _strategies_cache is not None:
        return _strategies_cache

    try:
        # JSON 파일 경로 설정
        json_path = Path(__file__).parent / "strategy.json"

        with open(json_path, 'r', encoding='utf-8') as f:
            strategies = json.load(f)

        logger.info(f"✅ JSON 파일에서 {len(strategies)}개의 전략을 로드했습니다.")
        _strategies_cache = strategies
        return strategies
    except Exception as e:
        logger.error(f"❌ JSON 파일 로드 중 오류: {e}")
        return []


async def get_or_create_default_user(db: AsyncSession) -> User:
    """
    기본 사용자를 가져오거나 생성합니다.
    user_id=1인 시스템 기본 사용자를 사용합니다.
    모든 하드코딩된 전략은 이 사용자(user_id=1)에게 속합니다.
    """
    try:
        result = await db.execute(select(User).where(User.user_id == 1))
        user = result.scalars().first()

        if user:
            logger.info(
                f"✅ 기본 사용자 확인: user_id={user.user_id}, name={user.name}, email={user.email}")
            return user

        # 기본 사용자가 없으면 생성
        logger.info("📝 기본 사용자(user_id=1)를 생성합니다...")
        default_user = User(
            name="admin",
            email="admin@capslock.com",
            password_hash=User.hash_password("capslock123!@#"),  # 기본 비밀번호
            is_active=True,
            role="ADMIN"
        )
        db.add(default_user)
        await db.commit()
        await db.refresh(default_user)
        logger.info(f"✅ 기본 사용자 생성 완료: user_id={default_user.user_id}")
        return default_user

    except Exception as e:
        logger.error(f"❌ 기본 사용자 생성 중 오류: {e}")
        await db.rollback()
        raise


async def seed_strategies(db: AsyncSession, user_id: int = 1) -> None:
    """
    기본 전략 데이터를 데이터베이스에 시딩합니다.
    이미 존재하는 전략은 건너뜁니다.

    Args:
        db: 데이터베이스 세션
        user_id: 전략을 생성할 사용자 ID (기본값: 1, 고정)
    """
    try:
        # 기본 사용자(user_id=1) 확인/생성
        user = await get_or_create_default_user(db)

        logger.info(f"🎯 user_id={user.user_id}로 전략을 시딩합니다.")

        # 기존 전략 확인 (user_id=1에 속한 전략들)
        result = await db.execute(
            select(Strategy).where(Strategy.user_id == user.user_id)
        )
        existing_strategies = result.scalars().all()
        existing_names = {s.strategy_name for s in existing_strategies}

        created_count = 0
        skipped_count = 0

        # JSON 파일에서 전략 데이터 로드
        strategies_data = load_strategies_from_json()

        if not strategies_data:
            logger.warning("⚠️  로드할 전략 데이터가 없습니다.")
            return

        for strategy_data in strategies_data:
            # JSON 파일의 키 이름 처리 (strategey_name 오타와 strategy_name 둘 다 지원)
            strategy_name = strategy_data.get(
                "strategey_name") or strategy_data.get("strategy_name")

            if strategy_name in existing_names:
                logger.info(f"⏭️  전략 '{strategy_name}'은 이미 존재합니다.")
                skipped_count += 1
                continue

            # 새 전략 생성 (user_id=1로 고정)
            strategy = Strategy(
                user_id=user.user_id,  # 항상 user_id=1
                strategy_name=strategy_name,
                description=strategy_data.get("description", ""),
                rules=strategy_data.get("rules", {})
            )
            db.add(strategy)
            created_count += 1
            logger.info(
                f"✅ 전략 '{strategy_name}'을 생성했습니다. (user_id={user.user_id})")

        if created_count > 0:
            await db.commit()
            logger.info(
                f"🎉 총 {created_count}개의 전략을 생성했습니다. (건너뜀: {skipped_count}개, user_id={user.user_id})")
        else:
            logger.info(
                f"ℹ️  모든 기본 전략이 이미 존재합니다. (총 {skipped_count}개, user_id={user.user_id})")

    except Exception as e:
        logger.error(f"❌ 전략 시딩 중 오류 발생: {e}")
        await db.rollback()
        raise


async def init_seed_data(db: AsyncSession) -> None:
    """
    모든 초기 데이터를 시딩합니다.
    앱 시작 시 자동으로 호출됩니다.

    - 기본 사용자 (user_id=1) 생성/확인
    - 기본 전략 5개 생성 (모두 user_id=1 소유)
    """
    logger.info("=" * 60)
    logger.info("🌱 초기 데이터 시딩 시작")
    logger.info("=" * 60)

    try:
        # user_id=1로 전략 시딩
        await seed_strategies(db, user_id=1)

        logger.info("=" * 60)
        logger.info("✅ 초기 데이터 시딩 완료")
        logger.info("=" * 60)
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ 초기 데이터 시딩 실패: {e}")
        logger.error("=" * 60)
        raise
