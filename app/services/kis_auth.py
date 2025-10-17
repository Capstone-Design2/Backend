from dotenv import load_dotenv
import os
import httpx
import asyncio
import logging
from datetime import datetime, timedelta

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
            cls._instance = super(KISAuthManager, cls).__new__(cls)
        return cls._instance

    async def _fetch_new_token(self) -> None:
        """KIS 서버로부터 새로운 액세스 토큰 발급"""
        url = f"{KIS_DOMAIN}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            if "access_token" not in data or "expires_in" not in data:
                raise RuntimeError(f"KIS 인증 응답 형식이 올바르지 않습니다: {data}")

            self._access_token = data["access_token"]
            expires_in = int(data["expires_in"])
            
            # 만료 시간보다 1분 먼저 갱신하도록 버퍼를 둡니다.
            self._token_expires_at = utc_now() + timedelta(seconds=expires_in - 60)
            logger.info(f"새로운 KIS 액세스 토큰 발급 성공. 만료 시각: {self._token_expires_at}")

        except httpx.HTTPStatusError as e:
            logger.error(f"KIS 토큰 발급 API 요청 실패: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"KIS 인증 실패: {e.response.text}") from e
        except Exception as e:
            logger.error(f"KIS 토큰 발급 중 예외 발생: {e}")
            raise

    async def get_access_token(self) -> str:
        """유효한 액세스 토큰을 반환 or 만료되었으면 새로 발급"""
        async with self._lock:
            if not self._access_token or not self._token_expires_at or utc_now() >= self._token_expires_at:
                await self._fetch_new_token()
            
            assert self._access_token is not None, "토큰 발급 후에도 _access_token이 None입니다."
            return self._access_token

    async def get_approval_key(self) -> str:
        """웹소켓 접속을 위한 실시간 접속키(approval_key)를 발급받습니다."""
        url = f"{KIS_DOMAIN}/oauth2/Approval"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "secretkey": self.appsecret,
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            approval_key = data.get("approval_key")
            if not approval_key:
                raise RuntimeError(f"웹소켓 접속키 발급 실패: {data}")
            logger.info("웹소켓 접속키 발급 성공")
            return approval_key
        except Exception as e:
            logger.error(f"웹소켓 접속키 발급 중 예외 발생: {e}")
            raise

# --- FastAPI 의존성 주입을 위한 설정 ---

# 애플리케이션 생명주기 동안 유지될 싱글톤 인스턴스
_kis_auth_manager_instance = KISAuthManager()

def get_kis_auth_manager() -> KISAuthManager:
    """FastAPI 의존성 주입을 통해 KISAuthManager 싱글톤 인스턴스를 반환"""
    return _kis_auth_manager_instance