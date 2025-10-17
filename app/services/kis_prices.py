from enum import IntEnum
from typing import List, Dict, Literal, Optional
import httpx
from app.services.kis_auth import get_kis_auth_manager, KIS_API_BASE_URL, KIS_APP_KEY, KIS_APP_SECRET

Timeframe = Literal["1D", "1h", "30m", "15m", "5m", "1m"]

class MinuteUnit(IntEnum):
    m1 = 1
    m5 = 5
    m15 = 15
    m30 = 30
    m60 = 60

class KISPrices:
    """
    KIS 국내주식 시세 API 래퍼 (일/분봉)
    """
    def __init__(self) -> None:
        self._auth = get_kis_auth_manager()
        self._base_url = KIS_API_BASE_URL.rstrip("/")

    async def _headers(self) -> dict:
        token = await self._auth.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "custtype": "P",
            "tr_id": "FHKST03010100",
        }

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, headers=await self._headers(), timeout=15)

    # ---- 1) 일/주/월/년 봉 ----
    async def get_period_candles(
        self,
        kis_code: str,
        start_date: str,  # "YYYYMMDD"
        end_date: str,    # "YYYYMMDD"
        period: Literal["D","W","M","Y"] = "D",
    ) -> List[Dict]:
        """
        국내주식기간별시세(일_주_월_년)
        """
        url = "/quotations/inquire-daily-itemchartprice" 
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": kis_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": period,  # D/W/M/Y
            "FID_ORG_ADJ_PRC": "0",         # 0:비조정, 1:조정
        }
        async with await self._client() as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            j = r.json()

        rows = j.get("output") or j.get("output2") or []
        out: List[Dict] = []
        for it in rows:
            out.append({
                "date":   it.get("stck_bsop_date") or it.get("trd_dd"),
                "open":   it.get("stck_oprc") or it.get("opnprc"),
                "high":   it.get("stck_hgpr") or it.get("hgpr"),
                "low":    it.get("stck_lwpr") or it.get("lwpr"),
                "close":  it.get("stck_clpr") or it.get("clpr"),
                "volume": it.get("acml_tr_pbmn") or it.get("tvol"),
            })
        return out

    # ---- 2) 과거 분봉 ----
    async def get_intraday_by_date(
        self,
        kis_code: str,
        date: str,  # "YYYYMMDD"
        time_end: str = "153000",          # "HHMMSS" → 이 시각까지 역방향 최대 30개
        unit: Optional[int | MinuteUnit] = 1,  # 1/5/15/30/60 (있을 때만 전송)
    ) -> List[Dict]:
        """
        주식일별분봉조회
        """
        url = "/quotations/inquire-time-dailychartprice"
        unit_val: Optional[int] = None if unit is None else int(unit)

        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": kis_code,
            "fid_input_date_1": date,
            "fid_input_hour_1": str(time_end),  # HHMMSS
        }
        
        if unit_val is not None:
            params["fid_input_hour_2"] = f"{unit_val:02d}"  # 01/05/15/30/60

        async with await self._client() as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            j = r.json()

        rows = j.get("output") or []
        out: List[Dict] = []
        for it in rows:
            out.append({
                "date":   it.get("stck_bsop_date") or date,
                "time":   it.get("stck_trd_tm") or it.get("trd_tm"),
                "open":   it.get("stck_oprc") or it.get("opnprc"),
                "high":   it.get("stck_hgpr") or it.get("hgpr"),
                "low":    it.get("stck_lwpr") or it.get("lwpr"),
                "close":  it.get("stck_prpr") or it.get("clpr"),
                "volume": it.get("acml_tr_pbmn") or it.get("tvol"),
            })
        return out

    # ---- 3) 당일 분봉 ----
    async def get_intraday_today(
        self,
        kis_code: str,
        unit: Literal[1,5,15,30,60] = 1,
    ) -> List[Dict]:
        """
        주식당일분봉조회
        """
        url = "/quotations/inquire-time-itemchartprice"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": kis_code,
            "fid_input_hour_1": f"{unit:02d}",
        }
        async with await self._client() as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            j = r.json()

        rows = j.get("output") or []
        out: List[Dict] = []
        for it in rows:
            out.append({
                "date":   it.get("stck_bsop_date"),
                "time":   it.get("stck_trd_tm"),
                "open":   it.get("stck_oprc"),
                "high":   it.get("stck_hgpr"),
                "low":    it.get("stck_lwpr"),
                "close":  it.get("stck_prpr"),
                "volume": it.get("acml_tr_pbmn"),
            })
        return out
