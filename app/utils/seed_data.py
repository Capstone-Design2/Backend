# app/utils/seed_data.py
"""
초기 데이터 시딩 유틸리티
- 앱 시작 시 자동으로 실행되어 JSON 기반 기본 전략을 DB에 동기화함
- 같은 이름의 전략이 있더라도 JSON 내용이 변경되면 자동 업데이트
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


def load_strategies_from_json() -> List[dict]:
    """항상 최신 JSON 파일에서 전략 리스트를 로드합니다."""
    try:
        json_path = Path(__file__).parent / "strategy.json"
        with open(json_path, "r", encoding="utf-8") as f:
            strategies = json.load(f)
        return strategies
    except Exception as e:
        logger.error(f"JSON 파일 로드 중 오류: {e}")
        return []


async def get_or_create_default_user(db: AsyncSession) -> User:
    """user_id=1인 기본 사용자(admin)를 가져오거나 생성합니다."""
    try:
        result = await db.execute(select(User).where(User.user_id == 1))
        user = result.scalars().first()

        if user:
            return user

        default_user = User(
            name="admin",
            email="admin@capslock.com",
            password_hash=User.hash_password("capslock123!@#"),
            is_active=True,
            role="ADMIN"
        )
        db.add(default_user)
        await db.commit()
        await db.refresh(default_user)
        return default_user

    except Exception as e:
        logger.error(f"기본 사용자 생성 중 오류: {e}")
        await db.rollback()
        raise


async def seed_strategies(db: AsyncSession) -> None:
    """
    JSON 기반 전략 데이터를 DB에 자동 반영합니다.
    - 새 전략은 추가
    - 기존 전략은 JSON 내용이 바뀌면 자동 업데이트
    """
    try:
        user = await get_or_create_default_user(db)

        result = await db.execute(select(Strategy).where(Strategy.user_id == user.user_id))
        existing_strategies = result.scalars().all()
        existing_map = {s.strategy_name: s for s in existing_strategies}

        strategies_data = load_strategies_from_json()
        if not strategies_data:
            logger.warning("로드할 전략 데이터가 없습니다.")
            return

        created_count = 0
        updated_count = 0

        for strategy_data in strategies_data:
            strategy_name = strategy_data.get("strategy_name") or strategy_data.get("strategey_name")
            desc = strategy_data.get("description", "")

            existing = existing_map.get(strategy_name)

            if existing:
                # 기존 전략을 전체 전략 dict 기준으로 비교/업데이트
                full_spec = strategy_data
                if existing.rules != full_spec or (desc and existing.description != desc):
                    existing.rules = full_spec
                    existing.description = desc
                    updated_count += 1
                continue

            # 새 전략 추가
            new_strategy = Strategy(
                user_id=user.user_id,
                strategy_name=strategy_name,
                description=desc,
                rules=strategy_data,
            )
            db.add(new_strategy)
            created_count += 1

        await db.commit()

        if created_count > 0 or updated_count > 0:
            logger.info(f"전략 시딩 완료: {created_count}개 추가, {updated_count}개 업데이트")

    except Exception as e:
        logger.error(f"전략 시딩 중 오류: {e}")
        await db.rollback()
        raise


async def init_seed_data(db: AsyncSession) -> None:
    """앱 시작 시 자동으로 호출되어 전체 초기 데이터 시딩 수행"""
    try:
        await seed_strategies(db)
    except Exception as e:
        logger.error(f"초기 데이터 시딩 실패: {e}")
        raise
