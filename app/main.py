"""
Main.py works as a main function for the application
Api app starts from here
"""

from contextlib import asynccontextmanager
from logging import getLogger
from logging.config import dictConfig
from os import environ

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.routers import user_router
from app.utils.logger import sample_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


logger = getLogger(__name__)

app = FastAPI(
    docs_url=(
        "/caps_lock/api/docs"
        if environ.get("DEPLOY_PHASE", "dev") == "dev"
        or environ.get("DEPLOY_PHASE", "dev") == "local"
        else None
    ),
    lifespan=lifespan,
)

dictConfig(sample_logger)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # 실패한 요청에 대한 자세한 정보를 로그로 남깁니다.
    logger.error(
        f"Invalid request: {request.__dict__} - Errors: {exc.errors()}")
    # 클라이언트에게 구체적인 에러 메시지를 반환합니다.
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


origins = [
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(user_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}
