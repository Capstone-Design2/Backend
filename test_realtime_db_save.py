"""
실시간 시세 DB 저장 테스트 스크립트
Price Data Recorder가 제대로 동작하는지 확인
"""
import asyncio
import sys
from datetime import datetime, timezone
from sqlalchemy import select, desc

sys.path.insert(0, ".")

from app.database import get_session
from app.models.price_data import PriceData


async def check_realtime_data():
    """
    최근 1분봉 데이터 조회 (source='KIS_REALTIME')
    """
    print("=" * 70)
    print("실시간 시세 DB 저장 확인 테스트")
    print("=" * 70)

    async for db in get_session():
        try:
            # 최근 10개의 1분봉 데이터 조회 (KIS_REALTIME 소스)
            stmt = (
                select(PriceData)
                .where(PriceData.source == "KIS_REALTIME")
                .where(PriceData.timeframe == "1m")
                .order_by(desc(PriceData.timestamp))
                .limit(10)
            )

            result = await db.execute(stmt)
            records = result.scalars().all()

            if not records:
                print("\n❌ KIS_REALTIME 소스의 1분봉 데이터가 없습니다.")
                print("   - 서버가 실행 중인지 확인하세요.")
                print("   - SAVE_REALTIME_TO_DB=true 인지 확인하세요.")
                print("   - KIS Price Poller가 시세를 받고 있는지 확인하세요.")
                return

            print(f"\n✅ 실시간 1분봉 데이터 발견: 총 {len(records)}개")
            print("\n최근 데이터:")
            print("-" * 70)
            print(f"{'Ticker ID':<12} {'Timestamp (UTC)':<22} {'OHLC':<40}")
            print("-" * 70)

            for record in records:
                ohlc_str = f"O:{float(record.open):>8.0f} H:{float(record.high):>8.0f} L:{float(record.low):>8.0f} C:{float(record.close):>8.0f}"
                ts_str = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                print(f"{record.ticker_id:<12} {ts_str:<22} {ohlc_str}")

            # 가장 최근 데이터 상세 정보
            latest = records[0]
            print("\n" + "=" * 70)
            print("📊 가장 최근 1분봉 상세:")
            print("-" * 70)
            print(f"  Ticker ID    : {latest.ticker_id}")
            print(f"  Timestamp    : {latest.timestamp} (UTC)")
            print(f"  Timeframe    : {latest.timeframe}")
            print(f"  Open         : ₩{float(latest.open):,.0f}")
            print(f"  High         : ₩{float(latest.high):,.0f}")
            print(f"  Low          : ₩{float(latest.low):,.0f}")
            print(f"  Close        : ₩{float(latest.close):,.0f}")
            print(f"  Volume       : {latest.volume:,}")
            print(f"  Source       : {latest.source}")
            print(f"  Updated At   : {latest.updated_at}")
            print("=" * 70)

            # 데이터 업데이트 주기 확인
            if len(records) >= 2:
                time_diff = (records[0].timestamp - records[1].timestamp).total_seconds()
                print(f"\n⏱️  마지막 두 데이터 간격: {time_diff:.0f}초")
                print(f"   (KIS_POLL_INTERVAL 설정값과 유사해야 정상)")

        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

    print("\n" + "=" * 70)
    print("💡 팁:")
    print("   - 1분봉 데이터는 같은 분 내에서는 OHLC가 업데이트됩니다.")
    print("   - 새로운 분이 시작되면 새 레코드가 생성됩니다.")
    print("   - KIS_POLL_INTERVAL 간격으로 데이터가 업데이트됩니다.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(check_realtime_data())
