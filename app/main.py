"""
Main.py works as a main function for the application
Api app starts from here
"""

from contextlib import asynccontextmanager
from logging import getLogger
from logging.config import dictConfig
from os import environ
from types import SimpleNamespace

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database import get_session, init_db
from app.routers import (price_router, strategy_router, ticker_router,
                        user_router, auth_router, tradingview_router,
                        backtest as backtest_router)
from app.utils.dependencies import get_current_user
from app.utils.logger import sample_logger
from app.utils.seed_data import init_seed_data


# ----------------------------------------------------------------------
# Lifespan: 앱 시작 시 DB 초기화
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # 초기 데이터 시딩 (기본 전략 등)
    async for session in get_session():
        try:
            await init_seed_data(session)
        except Exception as e:
            logger.error(f"데이터 시딩 중 오류 발생: {e}")
        break  # 첫 번째 세션만 사용 (get_session()이 자동으로 close 처리)

    yield


logger = getLogger(__name__)

# ----------------------------------------------------------------------
# 환경 변수 로드 (.env)
# ----------------------------------------------------------------------
# load_dotenv() 환경변수 로드 대신 config.py에서 로드

# ----------------------------------------------------------------------
# FastAPI 애플리케이션 생성
# ----------------------------------------------------------------------
app = FastAPI(
    title="Algorithm Trading System",
    description="FastAPI 기반 알고리즘 트레이딩 백엔드 API",
    version="1.0.0",
    docs_url=(
        "/caps_lock/api/docs"
        if environ.get("DEPLOY_PHASE", "dev") in ("dev", "local")
        else None
    ),
    lifespan=lifespan,
)

# ----------------------------------------------------------------------
# User 인증 생략
# ----------------------------------------------------------------------
if settings.SKIP_AUTH and settings.DEPLOY_PHASE in ("dev", "local"):
    def _fake_current_user():
        # 필요하면 DB에서 1번 유저를 읽어 반환하도록 바꿔도 됨
        return SimpleNamespace(user_id=1, email="dev@example.com", name="Dev User", role="admin")
    app.dependency_overrides[get_current_user] = _fake_current_user

# ----------------------------------------------------------------------
# 로거 설정
# ----------------------------------------------------------------------
dictConfig(sample_logger)

# ----------------------------------------------------------------------
# 예외 핸들러
# ----------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(
        f"Invalid request: {request.__dict__} - Errors: {exc.errors()}"
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# ----------------------------------------------------------------------
# CORS 설정
# ----------------------------------------------------------------------
origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# 라우터 등록
# ----------------------------------------------------------------------
app.include_router(auth_router)  # JWT 관련 라우터 등록
app.include_router(user_router)  # 사용자 CRUD 라우터 등록
app.include_router(ticker_router)  # ticker 라우터 등록
app.include_router(price_router)  # price 라우터 등록
app.include_router(strategy_router)  # strategy 라우터 등록
app.include_router(tradingview_router)  # tradingview 라우터 등록
app.include_router(backtest_router.router) # backtest 라우터 등록

# ----------------------------------------------------------------------
# 기본 라우트
# ----------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "Hello, World!"}
