from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticker import Ticker
from app.schemas.ticker import TickerSyncResponse
from app.utils.mst_parser import parse_mst_zip

FILE_TO_MARKET_MAP = {
    "kospi_code.mst.zip": "KOSPI",
    "kosdaq_code.mst.zip": "KOSDAQ",
    "konex_code.mst.zip": "KONEX",
    "nxt_kospi_code.mst.zip": "KOSPI",
    "nxt_kosdaq_code.mst.zip": "KOSDAQ",
}

SYMBOL_SUFFIX = {
    "KOSPI": "KS",
    "KOSDAQ": "KQ",
    "KONEX": "KN",
}


def _safe_name(name: str | None, limit: int = 100) -> str | None:
        if not name:
            return None
        name = name.strip()
        if len(name) > limit:
            name = name[:limit]
        return name

def compose_symbol(kis_code: str, market: str) -> str:
    """
    심볼 표준화: 005930.KS / 091990.KQ ...
    미지정 시장은 kis_code 그대로 반환
    """
    suf = SYMBOL_SUFFIX.get(market)
    return f"{kis_code}.{suf}" if suf else kis_code

class TickerService:
    def __init__(self, auth_manager=None) -> None:
        self.auth = auth_manager  

    async def _upsert_batch(self, db: AsyncSession, rows: list[dict]) -> int:
        if not rows:
            return 0

        payload = []
        for r in rows:
            kis_code = r["pdno"]
            market = r["market"]
            symbol = compose_symbol(kis_code, market)
            company_name = _safe_name(r.get("name"))
            isin = r.get("isin")

            payload.append({
                "symbol":       symbol,
                "kis_code":     kis_code,
                "company_name": company_name,
                "market":       market,
                "currency":     "KRW",
                "isin":         isin,
                "is_deleted":   False,
            })

        # isin 유니크 제약 기반으로 업서트
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

        # (market, symbol) 유니크 기반으로 업서트
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
        files = [p for p in directory.iterdir() if p.name.lower().endswith(".mst.zip")]
        processed = 0

        for f in files:
            fname = f.name.lower()
            market = FILE_TO_MARKET_MAP.get(fname)
            if not market:
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
                synced += await self._upsert_batch(db, rows[i:i+BATCH])

            per_market[market] = per_market.get(market, 0) + synced
            total += synced
            processed += 1

        await db.commit()
        return TickerSyncResponse(
            total_synced=total,
            per_market_counts=per_market,
            files_processed=processed,
            notes="(market, symbol)로 업서트. 심볼은 kis_code + market suffix사로 구성됨",
        )
