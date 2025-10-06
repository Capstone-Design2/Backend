"""
Main.py works as a main function for the application
Api app starts from here
"""

from contextlib import asynccontextmanager
from logging import getLogger
from logging.config import dictConfig
from os import environ

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.routers import user_router
from app.routers.auth_router import router as auth_router  # ✅ 추가
from app.utils.logger import sample_logger

# ----------------------------------------------------------------------
# Lifespan: 앱 시작 시 DB 초기화
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


logger = getLogger(__name__)

# ----------------------------------------------------------------------
# 환경 변수 로드 (.env)
# ----------------------------------------------------------------------
load_dotenv()

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
app.include_router(auth_router)  # ✅ JWT 관련 라우터 등록
app.include_router(user_router)  # 사용자 CRUD 라우터 등록

# ----------------------------------------------------------------------
# 기본 라우트
# ----------------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "Hello, World!"}
