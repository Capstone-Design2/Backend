import logging
import os
from contextlib import asynccontextmanager
from os import environ
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlmodel import SQLModel

from app.models import User

logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", f"postgresql+asyncpg://{environ['DB_USER']}:{environ['DB_PWD']}@{environ['DB_HOST']}:5432/{environ['DB_NAME']}")

engine = create_async_engine(
    DATABASE_URL,
    # echo=os.getenv("ENV", "development") == "development", ORM 쿼리 로깅
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=True
)


@asynccontextmanager
async def get_async_session_context():
    """비동기 DB 세션 컨텍스트 매니저"""
    async with async_session() as session:
        yield session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """비동기 DB 세션 생성 - FastAPI Dependency Injection용"""
    session = async_session()
    try:
        yield session
    finally:
        # 세션 종료 시 안전하게 처리
        try:
            await session.close()
        except Exception as e:
            # 이미 닫혔거나 다른 작업 중인 경우 무시
            logger.debug(f"Session close warning (safe to ignore): {e}")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
