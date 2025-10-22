from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_session
from app.schemas.ticker import TickerSyncRequest, TickerSyncResponse
from app.services.ticker import TickerService
from app.utils.dependencies import get_current_user, get_ticker_service
from app.utils.router import get_router

router = get_router("ticker")


@router.post(
    "/sync",
    response_model=TickerSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="티커 파일 동기화 (*.mst.zip)",
    description="""
    로컬 디렉터리 내 종목정보 파일을 파싱해 ticker 테이블로 upsert합니다.
    """,
)
async def sync_tickers_from_files(
    body: TickerSyncRequest,
    service: Annotated[TickerService, Depends(get_ticker_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(get_current_user)],
):
    # 설정값 우선
    base_dir = settings.MST_DIR  # Path 객체
    dir_path = Path(body.directory) if body.directory else base_dir

    if not dir_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"MST directory not found: {dir_path}. "
            f"Set via request body or settings.MST_DIR"
        )

    try:
        resp = await service.sync_from_mst_directory(db, dir_path)
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sync failed: {e}")


@router.get("/")
async def get_ticker_by_name(
    name: str,
    service: Annotated[TickerService, Depends(get_ticker_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(get_current_user)],
):
    return await service.get_ticker_by_name(name, db)
