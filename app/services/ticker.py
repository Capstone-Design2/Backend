from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticker import Ticker
from app.schemas.ticker import TickerSyncResponse
from app.utils.mst_parser import parse_mst_zip

ALLOWED_MARKETS = {"KOSPI", "KOSDAQ", "KONEX"}

# 파일명에서 자동 추론
def _guess_market_from_filename(filename: str) -> Optional[str]:
    """
    파일명으로 시장을 추정한다.
    - kospi_code.mst.zip / nxt_kospi_code.mst.zip -> KOSPI
    - kosdaq_code.mst.zip / nxt_kosdaq_code.mst.zip -> KOSDAQ
    - konex_code.mst.zip -> KONEX
    그 외는 None 반환(스킵)
    """
    name = filename.lower()
    if "kospi" in name:
        return "KOSPI"
    if "kosdaq" in name:
        return "KOSDAQ"
    if "konex" in name:
        return "KONEX"
    return None

# 심볼 suffix
SYMBOL_SUFFIX = {
    "KOSPI":  "KS",
    "KOSDAQ": "KQ",
    "KONEX":  "KN",
}

SIX_DIGIT = re.compile(r"^\d{6}$")

def _safe_name(name: Optional[str], limit: int = 100) -> Optional[str]:
    if not name:
        return None
    name = name.strip()
    if len(name) > limit:
        name = name[:limit]
    return name

def _compose_symbol_from_pdno(pdno: str, market: str) -> str:
    suf = SYMBOL_SUFFIX.get(market, market.upper())
    return f"{pdno}.{suf}"

def _derive_kis_code_from_pdno(pdno: str) -> Optional[str]:
    return pdno if SIX_DIGIT.match(pdno) else None


class TickerService:
    def __init__(self, auth_manager=None) -> None:
        self.auth = auth_manager

    async def _upsert_batch(self, db: AsyncSession, rows: List[dict]) -> int:
        if not rows:
            return 0

        payload: List[dict] = []
        for r in rows:
            pdno: str = r["pdno"]
            market: str = r["market"]
            
            if market not in ALLOWED_MARKETS:
                continue

            symbol = _compose_symbol_from_pdno(pdno, market)
            company_name = _safe_name(r.get("name"))
            isin = r.get("isin")
            kis_code = _derive_kis_code_from_pdno(pdno)

            payload.append({
                "symbol":       symbol,
                "kis_code":     kis_code,      
                "company_name": company_name,
                "market":       market,
                "currency":     "KRW",
                "isin":         isin,
                "is_deleted":   False,
            })

        if not payload:
            return 0

        # ISIN 유니크 제약 기반 업서트
        with_isin = [p for p in payload if p.get("isin")]
        if with_isin:
            stmt1 = insert(Ticker).values(with_isin)
            stmt1 = stmt1.on_conflict_do_update(
                constraint="tickers_isin_key",
                set_={
                    "company_name": stmt1.excluded.company_name,
                    "kis_code":     stmt1.excluded.kis_code,
                    "market":       stmt1.excluded.market,
                    "currency":     stmt1.excluded.currency,
                    "is_deleted":   False,
                    "updated_at":   func.now(),
                    "symbol":       stmt1.excluded.symbol,
                },
            )
            await db.execute(stmt1)

        # (market, symbol) 유니크 기반 업서트
        without_isin = [p for p in payload if not p.get("isin")]
        if without_isin:
            stmt2 = insert(Ticker).values(without_isin)
            stmt2 = stmt2.on_conflict_do_update(
                index_elements=[Ticker.market, Ticker.symbol],
                set_={
                    "company_name": stmt2.excluded.company_name,
                    "kis_code":     stmt2.excluded.kis_code,
                    "currency":     stmt2.excluded.currency,
                    "is_deleted":   False,
                    "updated_at":   func.now(),
                    "isin":         stmt2.excluded.isin,
                },
            )
            await db.execute(stmt2)

        return len(payload)

    async def sync_from_mst_directory(self, db: AsyncSession, directory: Path) -> TickerSyncResponse:
        assert directory.exists(), f"MST directory not found: {directory}"

        total = 0
        per_market: Dict[str, int] = {}
        files = [p for p in directory.iterdir() if p.suffix.lower() in {".zip", ".mst"} or p.name.lower().endswith(".mst.zip")]
        processed = 0

        for f in sorted(files, key=lambda p: p.name.lower()):
            market = _guess_market_from_filename(f.name)
            
            if market not in ALLOWED_MARKETS:
                processed += 1
                continue

            rows = parse_mst_zip(f, default_market=market)
            if not rows:
                per_market.setdefault(market, 0)
                processed += 1
                continue

            BATCH = 5000
            synced = 0
            for i in range(0, len(rows), BATCH):
                synced += await self._upsert_batch(db, rows[i:i + BATCH])

            per_market[market] = per_market.get(market, 0) + synced
            total += synced
            processed += 1

        await db.commit()
        return TickerSyncResponse(
            total_synced=total,
            per_market_counts=per_market,
            files_processed=processed,
        )
        
    async def load_kis_to_ticker_id(self, db) -> Dict[str, int]:
        """
        tickers 테이블에서 (kis_code -> ticker_id) 맵 생성
        - 주식 3시장 (KOSPI/KOSDAQ/KONEX)
        """
        stmt = (
            select(
                Ticker.__table__.c.kis_code,
                Ticker.__table__.c.ticker_id,
            )
            .where(Ticker.__table__.c.market.in_(["KOSPI", "KOSDAQ", "KONEX"]))
            .where(Ticker.__table__.c.kis_code.isnot(None))
        )
        rows = (await db.execute(stmt)).all()
        return {kis: tid for kis, tid in rows if kis and SIX_DIGIT.fullmatch(kis)}
    
    async def resolve_one(
        self, db, *, kis_code: Optional[str] = None, symbol: Optional[str] = None
    ) -> Tuple[int, str]:
        """
        단일 종목 식별자 → (ticker_id, kis_code) 반환
        - kis_code 우선. 없으면 symbol로 조회.
        - 둘 다 없으면 ValueError
        - 못 찾으면 LookupError
        """
        if not kis_code and not symbol:
            raise ValueError("kis_code 또는 symbol 중 하나는 필수입니다.")

        if kis_code:
            stmt = select(
                Ticker.__table__.c.ticker_id,
                Ticker.__table__.c.kis_code,
            ).where(Ticker.__table__.c.kis_code == kis_code)
        else:
            stmt = select(
                Ticker.__table__.c.ticker_id,
                Ticker.__table__.c.kis_code,
            ).where(Ticker.__table__.c.symbol == symbol)

        row = (await db.execute(stmt)).first()
        if not row:
            raise LookupError(f"해당 종목을 찾을 수 없습니다. (kis_code={kis_code}, symbol={symbol})")
        tid, kcode = row
        if not kcode or len(kcode) != 6:
            raise LookupError(f"해당 종목은 유효한 6자리 kis_code가 없습니다. (symbol={symbol})")
        return tid, kcode
        
