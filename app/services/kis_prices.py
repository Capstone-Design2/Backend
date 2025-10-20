# app/services/kis_prices.py
from __future__ import annotations

import asyncio, time, json, random
from collections import deque
from enum import IntEnum
from typing import List, Dict, Literal, Optional, Tuple
from datetime import datetime, timedelta, timezone

import httpx
from app.services.kis_auth import (
    get_kis_auth_manager,
    KIS_API_BASE_URL,   # 예: "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1"
    KIS_APP_KEY,
    KIS_APP_SECRET,
)

# =========================
# 레이트리밋/재시도 설정
# =========================
KIS_MAX_RPS = 5                    # 초당 최대 호출 수 (보수적으로 시작)
KIS_MAX_CONCURRENCY = 2            # 동시 요청 제한
KIS_RETRY_MAX = 4                  # 재시도 횟수
KIS_BACKOFF_BASE = 0.4             # 지수 백오프 base (초)
KIS_BACKOFF_JITTER = (0.05, 0.25)  # 지터(랜덤) 범위

# =========================
# 공통 유틸
# =========================
def _extract_time(it: Dict) -> Optional[str]:
    return (
        (it.get("stck_cntg_hour") or it.get("stck_trd_tm") or it.get("trd_tm") or it.get("time"))
        and str(it.get("stck_cntg_hour") or it.get("stck_trd_tm") or it.get("trd_tm") or it.get("time"))
    )

def _min_hhmmss(items: List[Dict]) -> Optional[str]:
    times = [t for t in (_extract_time(x) for x in items) if t and len(t) == 6 and t.isdigit()]
    return min(times) if times else None

def _dec_second(hhmmss: str) -> str:
    h = int(hhmmss[0:2]); m = int(hhmmss[2:4]); s = int(hhmmss[4:6])
    total = max(0, h*3600 + m*60 + s - 1)
    hh = total // 3600; mm = (total % 3600) // 60; ss = total % 60
    return f"{hh:02d}{mm:02d}{ss:02d}"

# =========================
# 시각/도메인 유틸
# =========================
KST = timezone(timedelta(hours=9))
API_PREFIX = "/uapi/domestic-stock/v1"

def _hhmmss(dt: datetime) -> str:
    return dt.strftime("%H%M%S")

def _today_kst_range(now: Optional[datetime] = None) -> tuple[str, str]:
    """
    KST 기준 장시작~장마감(09:00:00~15:30:00)
    - 장전: (09:00:00, 09:00:00)
    - 장중: (09:00:00, now)
    - 장후: (09:00:00, 15:30:00)
    """
    n = now.astimezone(KST) if now else datetime.now(KST)
    start = n.replace(hour=9, minute=0, second=0, microsecond=0)
    end_close = n.replace(hour=15, minute=30, second=0, microsecond=0)
    if n < start:
        return _hhmmss(start), _hhmmss(start)
    elif n <= end_close:
        return _hhmmss(start), _hhmmss(n)
    else:
        return _hhmmss(start), _hhmmss(end_close)

def _base_has_prefix(base_url: str) -> bool:
    return base_url.rstrip("/").endswith(API_PREFIX)

def _normalize_path(base_url: str, leaf: str) -> str:
    leaf = "/" + leaf.lstrip("/")
    return leaf if _base_has_prefix(base_url) else API_PREFIX + leaf

# =========================
# 간단 레이트리미터
# =========================
class _RateLimiter:
    def __init__(self, rps: int, concurrency: int):
        self.rps = max(1, rps)
        self.window = deque()
        self.lock = asyncio.Semaphore(max(1, concurrency))

    async def acquire(self):
        await self.lock.acquire()
        try:
            while True:
                now = time.monotonic()
                while self.window and now - self.window[0] > 1.0:
                    self.window.popleft()
                if len(self.window) < self.rps:
                    self.window.append(now)
                    return
                sleep_for = 1.0 - (now - self.window[0])
                await asyncio.sleep(max(0.01, sleep_for))
        finally:
            self.lock.release()

# =========================
# TR ID (실전/모의에 맞게 교체)
# =========================
TRID_DAILY_REAL        = "FHKST03010100"  # 기간별시세(일/주/월/년)
TRID_INTRADAY_TODAY    = "FHKST03010200"  # 당일 분봉
TRID_INTRADAY_BY_DATE  = "FHKST03010230"  # 일별 분봉 조회

# =========================
# 분봉 단위 Enum
# =========================
class MinuteUnit(IntEnum):
    m1 = 1
    m5 = 5
    m15 = 15
    m30 = 30
    m60 = 60

# =========================
# 메인 래퍼
# =========================
class KISPrices:
    """
    KIS 국내주식 시세 API 래퍼 (일/분봉)
    """
    def __init__(self) -> None:
        self._auth = get_kis_auth_manager()
        self._base_url = KIS_API_BASE_URL.rstrip("/")
        self._limiter = _RateLimiter(KIS_MAX_RPS, KIS_MAX_CONCURRENCY)
        self._client_obj: Optional[httpx.AsyncClient] = None

    async def _headers(self, tr_id: str) -> dict:
        token = await self._auth.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "custtype": "P",
            "tr_id": tr_id,
        }

    async def _client(self, tr_id: str) -> httpx.AsyncClient:
        # AsyncClient 재사용 + TR ID 갱신
        if self._client_obj is None or self._client_obj.is_closed:
            self._client_obj = httpx.AsyncClient(
                base_url=self._base_url,
                headers=await self._headers(tr_id),
                timeout=15,
            )
        else:
            self._client_obj.headers.update(await self._headers(tr_id))
        return self._client_obj

    async def aclose(self):
        if self._client_obj and not self._client_obj.is_closed:
            await self._client_obj.aclose()

    async def _get(self, tr_id: str, leaf_path: str, params: dict) -> dict:
        """
        안전 GET
        """
        path = _normalize_path(self._base_url, leaf_path)
        client = await self._client(tr_id)

        last_err = None
        for attempt in range(1, KIS_RETRY_MAX + 1):
            await self._limiter.acquire()

            resp = await client.get(path, params=params)
            text = resp.text
            status = resp.status_code

            if 200 <= status < 300:
                try:
                    j = resp.json()
                except Exception:
                    return {"raw": text}

                rt_cd = (j.get("rt_cd") or j.get("rtcd") or "").strip()
                if rt_cd in ("", "0"):
                    return j

                msg_cd = (j.get("msg_cd") or j.get("msgcd") or "").strip()
                if msg_cd in {"EGW00201", "EGW00202"}:
                    backoff = (KIS_BACKOFF_BASE * (2 ** (attempt - 1))) + random.uniform(*KIS_BACKOFF_JITTER)
                    await asyncio.sleep(backoff)
                    last_err = (status, msg_cd, text)
                    continue

                raise RuntimeError({
                    "where": "KIS_GET(rt_cd!=0)",
                    "status": status,
                    "msg_cd": msg_cd,
                    "text": text[:600],
                    "url": str(resp.request.url),
                    "params": params,
                })

            try:
                j = json.loads(text)
                msg_cd = (j.get("msg_cd") or "").strip()
            except Exception:
                j = None
                msg_cd = ""

            if msg_cd in {"EGW00201", "EGW00202"}:
                backoff = (KIS_BACKOFF_BASE * (2 ** (attempt - 1))) + random.uniform(*KIS_BACKOFF_JITTER)
                await asyncio.sleep(backoff)
                last_err = (status, msg_cd, text)
                continue

            resp.raise_for_status()

        # 재시도 모두 실패
        raise RuntimeError({
            "where": "KIS_GET(retry_exhausted)",
            "last_error": last_err,
            "url": f"{self._base_url}{path}",
            "params": params,
        })

    # ========== 1) 일/주/월/년 ==========
    async def get_period_candles(
        self,
        kis_code: str,
        start_date: str,  # "YYYYMMDD"
        end_date: str,    # "YYYYMMDD"
        period: Literal["D","W","M","Y"] = "D",
        adjusted: bool = False,
    ) -> List[Dict]:
        """
        국내주식기간별시세(일/주/월/년)
        """
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": kis_code,          # 6자리
            "fid_input_date_1": start_date,      # YYYYMMDD
            "fid_input_date_2": end_date,        # YYYYMMDD
            "fid_period_div_code": period,       # D/W/M/Y
            "fid_org_adj_prc": "1" if adjusted else "0",
        }
        j = await self._get(TRID_DAILY_REAL, "quotations/inquire-daily-itemchartprice", params)

        rows = j.get("output") or j.get("output2") or []
        out: List[Dict] = []
        for it in rows:
            out.append({
                "date":   it.get("stck_bsop_date") or it.get("trd_dd"),
                "open":   it.get("stck_oprc")      or it.get("opnprc"),
                "high":   it.get("stck_hgpr")      or it.get("hgpr"),
                "low":    it.get("stck_lwpr")      or it.get("lwpr"),
                "close":  it.get("stck_clpr")      or it.get("clpr"),
                # 거래량 우선 → 없으면 다른 필드로 폴백
                "volume": it.get("acml_vol") or it.get("acml_tr_vol") or it.get("tvol") or it.get("acml_tr_pbmn"),
            })
        return out

    # ========== 2) 과거 분봉(일자별) ==========
    async def get_intraday_by_date(
        self,
        kis_code: str,
        date: str,               # "YYYYMMDD"
    ) -> List[Dict]:
        """
        주식일별분봉조회(FHKST03010230): date일의 1분봉 전량 수집(30건 페이징)
        - 중복 제거 및 최종 오름차순 정렬
        - volume 우선순위: cntg_vol > tvol > (acml_vol 차분)    
        """
        async def _page(anchor_hms: str) -> List[Dict]:
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": kis_code,        # ex) 005930
                "FID_INPUT_DATE_1": date,          # ex) 20251020
                "FID_INPUT_HOUR_1": anchor_hms,    # ex) 153000
                "FID_PW_DATA_INCU_YN": "Y",
                "FID_FAKE_TICK_INCU_YN": "",       # 공백 필수
            }
            
            j = await self._get(
                TRID_INTRADAY_BY_DATE,
                "quotations/inquire-time-dailychartprice",
                params
            )
            rows = (j.get("output2") or j.get("output1") or j.get("output") or [])
            return rows if isinstance(rows, list) else []

        # 1) 15:30부터 09:00까지 당기기 (보통 정규장)
        all_rows: List[Dict] = []
        page_limit = 400  # 안전 가드(거의 도달하지 않음)
        seen_pages = 0
        
        # 첫 페이지
        items = await _page("153000")

        while True:
            all_rows.extend(items)

            # 가장 이른 체결시각
            times = [
                str(it.get("stck_cntg_hour") or it.get("stck_trd_tm") or it.get("trd_tm") or it.get("time"))
                for it in items
            ]
            times = [t for t in times if t and len(t) == 6 and t.isdigit()]
            earliest = min(times) if times else None

            # 더 당길 수 없거나 09:00 도달 시 종료
            if not earliest or earliest <= "090000":
                break

            # 다음 페이지 앵커 = earliest - 1초
            h = int(earliest[0:2]); m = int(earliest[2:4]); s = int(earliest[4:6])
            total = max(0, h*3600 + m*60 + s - 1)
            next_anchor = f"{total // 3600:02d}{(total % 3600)//60:02d}{total % 60:02d}"

            items = await _page(next_anchor)
            if not items:
                break

            seen_pages += 1
            if seen_pages >= page_limit:
                break  # 비정상 루프 방지

        # 2) (date,time) 기준 dedup + 정규화
        merged: Dict[Tuple[str, str], Dict] = {}
        for it in all_rows:
            d = str(it.get("stck_bsop_date") or date)
            t = str(it.get("stck_cntg_hour") or it.get("stck_trd_tm") or it.get("trd_tm") or it.get("time") or "")
            if not (len(d) == 8 and len(t) == 6 and t.isdigit()):
                continue
            merged[(d, t)] = {
                "date": d, "time": t,
                "open": it.get("stck_oprc") or it.get("opnprc"),
                "high": it.get("stck_hgpr") or it.get("hgpr"),
                "low":  it.get("stck_lwpr") or it.get("lwpr"),
                "close":it.get("stck_prpr") or it.get("clpr"),
                "cntg_vol": it.get("cntg_vol"),
                "tvol":     it.get("tvol"),
                "acml_vol": it.get("acml_vol"),  # 누적
            }

        # 3) 오름차순 정렬 + volume 결정(차분)
        normalized = sorted(merged.values(), key=lambda x: (x["date"], x["time"]))

        out: List[Dict] = []
        prev_acml = None
        prev_date = None
        for r in normalized:
            d, t = r["date"], r["time"]
            vol = None
            if r.get("cntg_vol") not in (None, ""):
                vol = r["cntg_vol"]
            elif r.get("tvol") not in (None, ""):
                vol = r["tvol"]
            else:
                curr = r.get("acml_vol")
                if curr not in (None, ""):
                    if prev_date != d:
                        prev_acml = None
                    if prev_acml is None:
                        vol = curr  # 첫 분봉은 누적 자체를 사용(또는 0으로 대체 가능)
                    else:
                        try:
                            vol = str(max(0, int(str(curr)) - int(str(prev_acml))))
                        except Exception:
                            vol = None
                    prev_acml = curr
                    prev_date = d

            out.append({
                "date": d, "time": t,
                "open": r.get("open"), "high": r.get("high"),
                "low":  r.get("low"),  "close": r.get("close"),
                "volume": vol,
            })
        return out

    # ========== 3) 당일 분봉(오늘) ==========
    async def get_intraday_today(
        self,
        kis_code: str,
    ) -> List[Dict]:
        """
        주식당일분봉조회: 오늘 1분봉 전량(30건 페이징)
        """
        async def _page(anchor_hms: str) -> List[Dict]:
            params = {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": kis_code,      # 6자리
                "fid_input_hour_1": anchor_hms,  # HHMMSS (끝시각 기준 30건)
                "fid_pw_data_incu_yn": "Y",       # 과거 데이터 포함
                "fid_etc_cls_code": "0",          # 기타 구분 코드(일반은 보통 '0')
            }
            j = await self._get(TRID_INTRADAY_TODAY, "quotations/inquire-time-itemchartprice", params)
            rows = (j.get("output2") or j.get("output1") or j.get("output") or [])
            return rows if isinstance(rows, list) else []

        # 1) 현재 시각 기준 → 09:00까지
        _, now_hms = _today_kst_range()  # ex) "142355"
        all_rows: List[Dict] = []
        anchor = now_hms
        while True:
            items = await _page(anchor)
            if not items:
                break
            all_rows.extend(items)
            times = [str(it.get("stck_cntg_hour") or it.get("stck_trd_tm") or it.get("trd_tm") or it.get("time")) for it in items]
            times = [t for t in times if t and len(t) == 6 and t.isdigit()]
            earliest = min(times) if times else None
            if not earliest or earliest <= "090000":
                break
            h = int(earliest[0:2]); m = int(earliest[2:4]); s = int(earliest[4:6])
            total = max(0, h*3600 + m*60 + s - 1)
            h = total // 3600; m = (total % 3600) // 60; s = total % 60
            anchor = f"{h:02d}{m:02d}{s:02d}"

        # 2) 정규화
        out: List[Dict] = []
        for it in all_rows:
            out.append({
                "date":   it.get("stck_bsop_date") or it.get("date"),
                "time":   it.get("stck_cntg_hour") or it.get("stck_trd_tm") or it.get("trd_tm") or it.get("time"),
                "open":   it.get("stck_oprc")      or it.get("open"),
                "high":   it.get("stck_hgpr")      or it.get("high"),
                "low":    it.get("stck_lwpr")      or it.get("low"),
                "close":  it.get("stck_prpr")      or it.get("close"),
                "volume": it.get("cntg_vol") or it.get("acml_vol") or it.get("tvol") or it.get("acml_tr_pbmn"),
            })
        return out
