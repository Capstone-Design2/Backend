from typing import Annotated
from pathlib import Path
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.ticker import TickerSyncRequest, TickerSyncResponse
from app.services.ticker import TickerService
from app.utils.router import get_router
from app.utils.dependencies import get_ticker_service, get_current_user
from app.core.config import settings

router = get_router("ticker")

@router.post(
    "/sync",
    response_model=TickerSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="티커 파일 동기화 (*.mst.zip)",
    description="""
    로컬 디렉터리 내 *.mst.zip(KOSPI/KOSDAQ/KONEX/NXT/ELW)을 파싱해 ticker 테이블로 업서트합니다.
    - 파일명 기준 시장 매핑: kospi_code.mst.zip → KOSPI, kosdaq_code.mst.zip → KOSDAQ, konex_code.mst.zip → KONEX 등
    - 업서트 키: (ticker_code, market)
    """,
)
async def sync_tickers_from_files(
    body: TickerSyncRequest,
    service: Annotated[TickerService, Depends(get_ticker_service)],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(get_current_user)],
):
    # 디렉터리 선택: 요청 바디 > settings.MST_DIR > 기본값
    dir_path = body.directory or getattr(settings, "MST_DIR", None) or "/mnt/data"
    try:
        resp = await service.sync_from_mst_directory(db, Path(dir_path))
        return resp
    except AssertionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sync failed: {e}")
