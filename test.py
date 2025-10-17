import asyncio
from app.utils.kis_auth import get_kis_access_token

async def test():
    token = await get_kis_access_token()
    print("✅ Access Token 발급 성공:", token[:20], "...")

asyncio.run(test())
