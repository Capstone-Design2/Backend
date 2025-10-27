from __future__ import annotations
from dotenv import load_dotenv
import os, httpx, asyncio, logging
from datetime import datetime, timedelta, timezone
from app.utils.datetime import utc_now

load_dotenv()

logger = logging.getLogger(__name__)

KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_DOMAIN = os.getenv("KIS_DOMAIN", "https://openapi.koreainvestment.com:9443") # 기본값: 실전투자
KIS_API_BASE_URL = f"{KIS_DOMAIN}/uapi/domestic-stock/v1"

if not KIS_APP_KEY or not KIS_APP_SECRET:
    logger.error("KIS_APP_KEY 또는 KIS_APP_SECRET 환경변수가 설정되지 않았습니다.")
    raise EnvironmentError(
        "KIS_APP_KEY 또는 KIS_APP_SECRET 환경변수가 설정되지 않았습니다."
    )

_SKEW = timedelta(minutes=2)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class KISAuthManager:
    """KIS API 인증 토큰을 관리하는 싱글톤 클래스"""

    _instance = None
    _lock = asyncio.Lock()

    _access_token: str | None = None
    _token_expires_at: datetime | None = None

    appkey: str = KIS_APP_KEY
    appsecret: str = KIS_APP_SECRET

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _is_valid(self) -> bool:
        return bool(self._access_token and self._token_expires_at and utc_now() + _SKEW < self._token_expires_at)

    async def _fetch_new_token(self) -> None:
        """KIS 서버로부터 새로운 액세스 토큰 발급"""
        url = f"{KIS_DOMAIN}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            logger.error("KIS 토큰 발급 실패: %s - %s", e.response.status_code, e.response.text)
            raise RuntimeError(f"KIS 인증 실패: {e.response.text}") from e

        token = data.get("access_token")
        if not token:
            logger.error("KIS 토큰 응답 비정상: %s", data)
            raise RuntimeError("KIS token issue failed: access_token missing")

        # 만료 파싱: expires_in(seconds) 우선, 없으면 access_token_token_expire("YYYY-MM-DD HH:MM:SS")
        expires_at: datetime
        if "expires_in" in data:
            try:
                sec = float(data["expires_in"])
            except Exception:
                sec = 24 * 3600.0
            expires_at = utc_now() + timedelta(seconds=max(60.0, sec))  # 최소 60초 보장
        else:
            expire_str = data.get("access_token_token_expire") or data.get("access_token_expire")
            if expire_str:
                # 문서별로 KST인 경우가 있어 보수적으로 UTC로 파싱 후 스큐로 보호
                try:
                    # 기본 포맷 가정
                    dt = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except Exception:
                    dt = utc_now() + timedelta(hours=24)
                expires_at = dt
            else:
                expires_at = utc_now() + timedelta(hours=24)

        self._access_token = token
        # 안전 스큐 적용(조기 갱신)
        self._token_expires_at = expires_at - _SKEW
        logger.info("KIS 토큰 발급 완료. 만료(스큐 적용 후): %s", self._token_expires_at.isoformat())


    async def get_access_token(self) -> str:
        if self._is_valid():
            return self._access_token  # type: ignore
        async with self._lock:
            if self._is_valid():
                return self._access_token  # type: ignore
            await self._fetch_new_token()
            return self._access_token  # type: ignore

    async def force_refresh(self) -> str:
        async with self._lock:
            await self._fetch_new_token()
            return self._access_token  # type: ignore

    async def get_approval_key(self) -> str:
        url = f"{KIS_DOMAIN}/oauth2/Approval"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecret": self.appsecret,   # ← secretkey → appsecret 로 정렬
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        approval_key = data.get("approval_key")
        if not approval_key:
            raise RuntimeError(f"웹소켓 접속키 발급 실패: {data}")
        return approval_key

# 모듈 단위 싱글톤 인스턴스(프로세스 단위)
_kis_auth_manager_instance = KISAuthManager()
def get_kis_auth_manager() -> KISAuthManager:
    return _kis_auth_manager_instance