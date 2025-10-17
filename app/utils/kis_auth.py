import os
import httpx

KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_BASE_URL = "https://openapivts.koreainvestment.com:29443"

if not KIS_APP_KEY or not KIS_APP_SECRET:
    raise EnvironmentError("KIS_APP_KEY 또는 KIS_APP_SECRET 환경변수가 설정되지 않았습니다.")

async def get_kis_access_token() -> str:
    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    
    if "access_token" not in data:
        raise RuntimeError(f"KIS 인증 실패: {data}")

    return data["access_token"]