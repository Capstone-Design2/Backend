from typing import Dict, List

def pricescale_from_decimals(decimals: int) -> int:
    d = max(0, min(int(decimals), 10))
    return 10 ** d

def build_symbol_meta_udf(meta: Dict) -> Dict:
    if (tick := meta.get("tick_size")) is not None:
        s = str(tick)
        decimals = len(s.split(".")[1].rstrip("0")) if "." in s else 0
        pricescale = pricescale_from_decimals(decimals)
        minmov = int(meta.get("minmov", 1))
    else:
        pricescale = pricescale_from_decimals(int(meta.get("price_decimals", 6)))
        minmov = int(meta.get("minmov", 1))

    return {
        "name": meta["symbol"],
        "ticker": meta["symbol"],
        "description": meta.get("description", meta["symbol"]),
        "exchange": meta.get("exchange", "CUSTOM"),
        "listed_exchange": meta.get("exchange", "CUSTOM"),
        "type": meta.get("type", "stock"),
        "session": meta.get("session", "0000-0000"),
        "timezone": meta.get("timezone", "UTC"),
        "minmov": minmov,
        "pricescale": pricescale,
        "pointvalue": 1,
        "has_intraday": True,
        "has_no_volume": False,
        "supported_resolutions": ["1","5","15","30","60","D"],
        "currency_code": meta.get("currency", "USD"),
    }

def build_history_udf(rows: List[Dict]) -> Dict:
    if not rows:
        return {"s": "no_data"}
    return {
        "s": "ok",
        "t": [r["t"] for r in rows],
        "o": [r["o"] for r in rows],
        "h": [r["h"] for r in rows],
        "l": [r["l"] for r in rows],
        "c": [r["c"] for r in rows],
        "v": [r["v"] for r in rows],
    }
