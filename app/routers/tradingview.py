from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional
from app.database import get_session
from app.utils.router import get_router
from app.core.tradingview import SUPPORTED_RESOLUTIONS

from fastapi import Query, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ticker import TickerRepository
from app.repositories.price import PriceRepository
from app.schemas.tradingview import SymbolMetaOut, HistoryOut, SearchItemOut
from app.services.tv_symbol import TVSymbolService
from app.services.tv_history import TVHistoryService

Resolution = Literal["1","5","15","30","60","D"]

router = get_router("tradingview")

@router.get(
    "/config",
    summary="TradingView 초기 설정",
    )
async def tv_config():
    return {
        "supports_search": True,           
        "supports_group_request": False,
        "supports_marks": False,
        "supports_timescale_marks": False,
        "supports_time": True,             
        "supported_resolutions": SUPPORTED_RESOLUTIONS,
    }

@router.get(
    "/time",
    summary="서버 시간",
    )
async def tv_time():
    return int(datetime.now(tz=timezone.utc).timestamp())

@router.get(
    "/symbols",
    response_model=SymbolMetaOut,
    summary="티커 메타 정보",
    )
async def tv_symbols(
    db: Annotated[AsyncSession, Depends(get_session)],
    t_repo: Annotated[TickerRepository, Depends(TickerRepository)],
    symbol: str = Query(..., alias="symbol"),
):
    try:
        svc = TVSymbolService(t_repo)
        data = await svc.get_symbol_meta_udf(symbol=symbol, db=db)
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get(
    "/history",
    response_model=HistoryOut,
    summary="OHLCV 데이터",
)
async def tv_history(
    db: Annotated[AsyncSession, Depends(get_session)],
    t_repo: Annotated[TickerRepository, Depends(TickerRepository)],
    p_repo: Annotated[PriceRepository, Depends(PriceRepository)],
    symbol: str = Query(..., alias="symbol"),
    resolution: Resolution = Query(..., alias="resolution"),
    _from: int = Query(..., alias="from"),
    _to: int = Query(..., alias="to"),
    adjusted: bool = Query(False),
):
    try:
        svc = TVHistoryService(t_repo, p_repo)
        return await svc.get_history_udf(
            symbol=symbol,
            start_ts = _from,
            end_ts = _to,
            resolution=resolution,
            adjusted=adjusted,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get(
    "/search",
    response_model=List[SearchItemOut],
    summary="심볼 검색",
)
async def tv_search(
    db: Annotated[AsyncSession, Depends(get_session)],
    t_repo: Annotated[TickerRepository, Depends(TickerRepository)],
    query: str = Query(..., alias="query"),
    limit: int = Query(30, ge=1, le=100),
    exchange: Optional[str] = Query(None, alias="exchange"),
):
    svc = TVSymbolService(t_repo)
    return await svc.search_udf(
        db=db, query=query, limit=limit, exchange=exchange
    )
    
