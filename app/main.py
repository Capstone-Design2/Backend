"""
Main.py works as a main function for the application
Api app starts from here
"""

from contextlib import asynccontextmanager
from logging import getLogger
from logging.config import dictConfig
from os import environ
from types import SimpleNamespace
import asyncio

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database import get_session, init_db
from app.routers import (price_router, strategy_router, ticker_router,
                        user_router, auth_router, tradingview_router,
                        paper_trading_router,
                        backtest as backtest_router, websocket as websocket_router)
from app.utils.dependencies import get_current_user
from app.utils.logger import sample_logger
from app.utils.seed_data import init_seed_data
from app.services.kis_websocket import get_kis_ws_client
from app.routers.websocket import broadcast_worker
from app.services.order_executor import get_order_executor


# ----------------------------------------------------------------------
# Lifespan: 앱 시작 시 DB 초기화 및 백그라운드 태스크 관리
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB 초기화
    await init_db()

    # 초기 데이터 시딩 (기본 전략 등)
    async for session in get_session():
        try:
            await init_seed_data(session)
        except Exception as e:
            logger.error(f"데이터 시딩 중 오류 발생: {e}")
        break  # 첫 번째 세션만 사용 (get_session()이 자동으로 close 처리)

    # 백그라운드 태스크 시작
    tasks = []

    # WebSocket 브로드캐스트 워커
    broadcast_task = asyncio.create_task(broadcast_worker())
    tasks.append(broadcast_task)
    logger.info("WebSocket 브로드캐스트 워커 시작됨")

    # Order Execution Engine
    order_executor = get_order_executor()
    executor_task = asyncio.create_task(order_executor.run())
    tasks.append(executor_task)
    logger.info("Order Executor 시작됨")

    # KIS WebSocket Client (선택적 - 환경 변수로 제어 가능)
    if environ.get("ENABLE_KIS_WEBSOCKET", "false").lower() == "true":
        kis_ws_client = get_kis_ws_client()

        async def kis_ws_task():
            try:
                await kis_ws_client.connect()
                # 기본 구독 종목 (환경 변수에서 읽기)
                default_tickers = environ.get("KIS_WS_DEFAULT_TICKERS", "005930,000660").split(",")
                await kis_ws_client.subscribe(default_tickers)
                await kis_ws_client.listen()
            except Exception as e:
                logger.error(f"KIS WebSocket 태스크 오류: {e}")

        kis_task = asyncio.create_task(kis_ws_task())
        tasks.append(kis_task)
        logger.info("KIS WebSocket 클라이언트 시작됨")

    yield

    # 앱 종료 시 백그라운드 태스크 정리
    logger.info("백그라운드 태스크 종료 중...")
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    # KIS WebSocket 연결 종료
    if environ.get("ENABLE_KIS_WEBSOCKET", "false").lower() == "true":
        try:
            kis_ws_client = get_kis_ws_client()
            await kis_ws_client.disconnect()
        except Exception as e:
            logger.error(f"KIS WebSocket 종료 오류: {e}")

    logger.info("백그라운드 태스크 정리 완료")


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
    # 사용자 친화적인 에러 메시지 생성
    errors = exc.errors()
    error_messages = []

    for error in errors:
        field = error.get("loc", [])[-1] if error.get("loc") else "unknown"
        msg = error.get("msg", "")

        # 한글 메시지로 변환
        if "at least" in msg and "characters" in msg:
            min_length = error.get("ctx", {}).get("min_length", "")
            error_messages.append(f"{field}는 최소 {min_length}자 이상으로 설정해주세요.")
        elif "valid email" in msg.lower():
            error_messages.append(f"{field}는 유효한 이메일 주소를 입력해주세요.")
        elif "missing" in msg.lower():
            error_messages.append(f"{field}는 필수 입력 항목입니다.")
        else:
            error_messages.append(f"{field}: {msg}")

    # 로그 출력
    for message in error_messages:
        logger.warning(message)

    return JSONResponse(
        status_code=422,
        content={"detail": errors}
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
app.include_router(paper_trading_router)  # paper trading 라우터 등록
app.include_router(backtest_router.router) # backtest 라우터 등록
app.include_router(websocket_router.router)  # WebSocket 라우터 등록

# ----------------------------------------------------------------------
# 기본 라우트
# ----------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "Hello, World!"}
