"""
KIS API 인증 및 WebSocket 연결 테스트 스크립트
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Backend 경로 추가
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

async def test_kis_connection():
    """KIS API 연결 테스트"""
    print("=" * 60)
    print("KIS API 연결 테스트 시작")
    print("=" * 60)

    # 환경 변수 확인
    KIS_APP_KEY = os.getenv("KIS_APP_KEY")
    KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
    KIS_DOMAIN = os.getenv("KIS_DOMAIN")

    print(f"\n[1] 환경 변수 확인")
    print(f"  - KIS_APP_KEY: {KIS_APP_KEY[:20]}... (총 {len(KIS_APP_KEY)}자)")
    print(f"  - KIS_APP_SECRET: {KIS_APP_SECRET[:20]}... (총 {len(KIS_APP_SECRET)}자)")
    print(f"  - KIS_DOMAIN: {KIS_DOMAIN}")

    if not KIS_APP_KEY or not KIS_APP_SECRET:
        print("\n[ERROR] 환경 변수가 설정되지 않았습니다!")
        return

    # Access Token 발급 테스트
    print(f"\n[2] Access Token 발급 테스트")
    try:
        from app.services.kis_auth import get_kis_auth_manager
        auth_manager = get_kis_auth_manager()

        print("  - Access Token 발급 시도 중...")
        token = await auth_manager.get_access_token()
        print(f"  [OK] Access Token 발급 성공: {token[:30]}...")
    except Exception as e:
        print(f"  [ERROR] Access Token 발급 실패: {e}")
        return

    # Approval Key 발급 테스트 (WebSocket용)
    print(f"\n[3] Approval Key 발급 테스트 (WebSocket)")
    try:
        print("  - Approval Key 발급 시도 중...")
        approval_key = await auth_manager.get_approval_key()
        print(f"  [OK] Approval Key 발급 성공: {approval_key[:30]}...")
    except Exception as e:
        print(f"  [ERROR] Approval Key 발급 실패: {e}")
        print(f"  → 이유: 403 오류는 보통 다음 원인입니다:")
        print(f"     1. 앱키가 실전투자용인데 모의투자 도메인 사용")
        print(f"     2. 앱키가 모의투자용인데 실전투자 도메인 사용")
        print(f"     3. 앱키/시크릿이 잘못됨")
        print(f"     4. API 사용 권한이 없거나 만료됨")
        return

    # WebSocket 연결 테스트
    print(f"\n[4] WebSocket 연결 테스트")
    try:
        from app.services.kis_websocket import get_kis_ws_client

        kis_client = get_kis_ws_client()
        print("  - WebSocket 연결 시도 중...")
        await kis_client.connect()
        print(f"  [OK] WebSocket 연결 성공!")

        print("\n[5] 종목 구독 테스트")
        print("  - 삼성전자(005930) 구독 중...")
        await kis_client.subscribe(["005930"])
        print(f"  [OK] 종목 구독 완료!")

        print("\n[6] 실시간 시세 수신 테스트 (10초간)")
        print("  - 실시간 데이터 대기 중...")

        async def print_price():
            from app.core.events import get_price_event_bus
            event_bus = get_price_event_bus()
            queue = event_bus.subscribe()

            count = 0
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < 10:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    count += 1
                    print(f"  [DATA {count}] {event.ticker_code}: {float(event.price):,.0f} KRW (vol: {event.volume:,})")
                except asyncio.TimeoutError:
                    continue

            if count == 0:
                print("  [WARN] 10초간 시세 데이터를 받지 못했습니다")
            else:
                print(f"  [OK] 총 {count}개의 시세 데이터 수신 성공!")

            event_bus.unsubscribe(queue)

        # 동시에 listen과 print_price 실행
        await asyncio.gather(
            asyncio.wait_for(kis_client.listen(), timeout=10),
            print_price(),
            return_exceptions=True
        )

        await kis_client.disconnect()

    except asyncio.TimeoutError:
        print("  [INFO] 타임아웃 (정상 - 테스트 완료)")
    except Exception as e:
        print(f"  [ERROR] WebSocket 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("[SUCCESS] 모든 테스트 완료!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_kis_connection())
