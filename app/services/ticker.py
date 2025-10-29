from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ticker import Ticker
from app.repositories.ticker import TickerRepository
from app.schemas.ticker import TickerSyncResponse
from app.utils.mst_parser import parse_mst_zip

ALLOWED_MARKETS = {"KOSPI", "KOSDAQ", "KONEX"}


# 심볼 suffix
SYMBOL_SUFFIX = {
    "KOSPI":  "KS",
    "KOSDAQ": "KQ",
    "KONEX":  "KN",
}

SIX_DIGIT = re.compile(r"^\d{6}$")


class TickerService:
    def __init__(self, auth_manager=None) -> None:
        self.auth = auth_manager
        self.ticker_repository = TickerRepository()

    @staticmethod
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

    @staticmethod
    def _safe_name(name: Optional[str], limit: int = 100) -> Optional[str]:
        if not name:
            return None
        name = name.strip()
        if len(name) > limit:
            name = name[:limit]
        return name

    @staticmethod
    def _compose_symbol_from_pdno(pdno: str, market: str) -> str:
        suf = SYMBOL_SUFFIX.get(market, market.upper())
        return f"{pdno}.{suf}"
    
    @staticmethod
    def _derive_kis_code_from_pdno(pdno: str) -> Optional[str]:
        return pdno if SIX_DIGIT.match(pdno) else None

    async def _upsert_batch(self, db: AsyncSession, rows: List[dict]) -> int:
        if not rows:
            return 0

        payload: List[dict] = []
        for r in rows:
            pdno: str = r["pdno"]
            market: str = r["market"]

            if market not in ALLOWED_MARKETS:
                continue

            symbol = self._compose_symbol_from_pdno(pdno, market)
            company_name = self._safe_name(r.get("name"))
            isin = r.get("isin")
            kis_code = self._derive_kis_code_from_pdno(pdno)

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
                index_elements=[Ticker.isin],
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

    async def get_ticker_by_name(self, name: str, db: AsyncSession) -> Optional[Ticker]:
        """회사명으로 티커를 조회합니다."""
        ticker = await self.ticker_repository.get_by_name(name, db)
        if not ticker:
            raise HTTPException(
                status_code=404,
                detail=f"종목을 찾을 수 없습니다: {name}"
            )
        return ticker

    async def sync_from_mst_directory(self, db: AsyncSession) -> TickerSyncResponse:

        # 설정값 우선
        directory = settings.MST_DIR

        if not directory.exists():
            raise HTTPException(
                status_code=400,
                detail=f"MST directory not found: {directory}. "
                f"Set via settings.MST_DIR"
            )

        assert directory.exists(), f"MST directory not found: {directory}"

        total = 0
        per_market: Dict[str, int] = {}
        files = [p for p in directory.iterdir() if p.suffix.lower(
        ) in {".zip", ".mst"} or p.name.lower().endswith(".mst.zip")]
        processed = 0

        for f in sorted(files, key=lambda p: p.name.lower()):
            market = self._guess_market_from_filename(f.name)

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
            raise LookupError(
                f"해당 종목을 찾을 수 없습니다. (kis_code={kis_code}, symbol={symbol})")
        tid, kcode = row
        if not kcode or len(kcode) != 6:
            raise LookupError(
                f"해당 종목은 유효한 6자리 kis_code가 없습니다. (symbol={symbol})")
        return tid, kcode
    
    async def load_kis_to_ticker_id(self, db: AsyncSession) -> Dict[str, int]:
        """
        KIS 6자리 코드 -> ticker_id 매핑을 전부 가져온다.
        - 삭제되지 않은(is_deleted=False) 종목만
        - 시장은 ALLOWED_MARKETS만 (KOSPI/KOSDAQ/KONEX)
        - kis_code가 존재하고 정확히 6자리인 것만
        """
        stmt = (
            select(
                Ticker.__table__.c.kis_code,
                Ticker.__table__.c.ticker_id,
            )
            .where(
                Ticker.__table__.c.is_deleted.is_(False),
                Ticker.__table__.c.market.in_(ALLOWED_MARKETS),
                Ticker.__table__.c.kis_code.is_not(None),
                func.length(Ticker.__table__.c.kis_code) == 6,
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        # 중복 kis_code가 우연히 있을 경우 첫 값만 채택
        mapping: Dict[str, int] = {}
        for kis_code, tid in rows:
            if kis_code and kis_code not in mapping:
                mapping[kis_code] = tid

        return mapping
