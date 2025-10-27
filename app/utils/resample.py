from __future__ import annotations
from typing import Any, Dict, List

# ---------- 리샘플링 유틸 ----------

def bucket_key_end(hhmmss: str, mins: int) -> str:
    h = int(hhmmss[0:2]); m = int(hhmmss[2:4])
    end_min = ((m // mins) + 1) * mins
    if end_min >= 60:
        h = (h + 1) % 24
        end_min -= 60
    return f"{h:02d}{end_min:02d}00"

def resample_from_1m(items_1m: List[Dict[str, Any]], mins: int) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in items_1m:
        t = r.get("time")
        if not t or len(t) != 6 or not str(t).isdigit():
            continue
        k = bucket_key_end(str(t), mins)
        o, h, l, c = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        v = r.get("volume")
        vol = int(v) if v is not None else 0
        b = buckets.get(k)
        if b is None:
            buckets[k] = {"date": r.get("date"), "time": k, "open": o, "high": h, "low": l, "close": c, "volume": vol}
        else:
            # high/low 갱신, close 갱신, volume 누적
            if h is not None: b["high"] = max(b["high"], h)
            if l is not None: b["low"]  = min(b["low"],  l)
            if c is not None: b["close"] = c
            b["volume"] += vol
    return list(buckets.values())

def rows_from_items(
    ticker_id: int,
    items: List[Dict[str, Any]],
    timeframe: str,
) -> List[Dict[str, Any]]:
    from app.utils.timezone import kst_ymd_to_utc_naive, kst_ymd_hms_to_utc_naive
    rows: List[Dict[str, Any]] = []
    if timeframe == "1D":
        for it in items:
            rows.append({
                "ticker_id": ticker_id,
                "timestamp": kst_ymd_to_utc_naive(it["date"]),
                "timeframe": "1D",
                "open": it.get("open"),
                "high": it.get("high"),
                "low": it.get("low"),
                "close": it.get("close"),
                "volume": it.get("volume"),
                "source": "KIS",
                "is_adjusted": False,
            })
    else:
        for it in items:
            rows.append({
                "ticker_id": ticker_id,
                "timestamp": kst_ymd_hms_to_utc_naive(str(it["date"]), str(it["time"])),
                "timeframe": timeframe,
                "open": it.get("open"),
                "high": it.get("high"),
                "low": it.get("low"),
                "close": it.get("close"),
                "volume": it.get("volume"),
                "source": "KIS",
                "is_adjusted": False,
            })
    return rows