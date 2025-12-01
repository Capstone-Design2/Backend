"""
KIS REST API Price Poller
WebSocket 대신 REST API로 주기적으로 현재가를 조회하여 PriceEvent 발행
모의투자 API에서 사용 가능
"""
import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import List
import httpx

from app.services.kis_auth import get_kis_auth_manager, KIS_DOMAIN
from app.core.events import get_price_event_bus, PriceEvent

logger = logging.getLogger(__name__)


class KISPricePoller:
    """
    KIS REST API로 주기적으로 현재가 조회
    모의투자 계좌에서도 실제 시세 데이터 사용 가능
    """

    def __init__(self, poll_interval: float = 2.0):
        """
        Args:
            poll_interval: 현재가 조회 간격 (초)
        """
        self.auth_manager = get_kis_auth_manager()
        self.event_bus = get_price_event_bus()
        self.poll_interval = poll_interval
        self.is_running = False
        self.subscribed_tickers: List[str] = []

    def subscribe(self, tickers: List[str]):
        """
        종목 구독 (현재가 조회 대상 추가)

        Args:
            tickers: 종목 코드 리스트 (예: ['005930', '000660'])
        """
        for ticker in tickers:
            if ticker not in self.subscribed_tickers:
                self.subscribed_tickers.append(ticker)
                logger.info(f"종목 구독 추가: {ticker}")

    async def _fetch_current_price(self, ticker_code: str) -> dict | None:
        """
        단일 종목의 현재가 조회

        Args:
            ticker_code: 종목 코드 (예: '005930')

        Returns:
            현재가 정보 dict 또는 None
        """
        try:
            token = await self.auth_manager.get_access_token()

            url = f"{KIS_DOMAIN}/uapi/domestic-stock/v1/quotations/inquire-price"
            headers = {
                "authorization": f"Bearer {token}",
                "appkey": self.auth_manager.appkey,
                "appsecret": self.auth_manager.appsecret,
                "tr_id": "FHKST01010100",  # 주식현재가 시세
            }
            params = {
                "fid_cond_mrkt_div_code": "J",  # 주식
                "fid_input_iscd": ticker_code,
            }

            # SSL 검증 비활성화 (모의투자 서버 인증서 문제)
            async with httpx.AsyncClient(timeout=5, verify=False) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

            if data.get("rt_cd") != "0":
                logger.warning(f"현재가 조회 실패: {ticker_code} - {data.get('msg1')}")
                return None

            output = data.get("output")
            if not output:
                return None

            return {
                "ticker_code": ticker_code,
                "stck_prpr": output.get("stck_prpr"),  # 현재가
                "prdy_vrss": output.get("prdy_vrss"),  # 전일대비
                "prdy_vrss_sign": output.get("prdy_vrss_sign"),  # 전일대비부호
                "prdy_ctrt": output.get("prdy_ctrt"),  # 전일대비율
                "acml_vol": output.get("acml_vol"),  # 누적거래량
                "stck_hgpr": output.get("stck_hgpr"),  # 최고가
                "stck_lwpr": output.get("stck_lwpr"),  # 최저가
                "stck_oprc": output.get("stck_oprc"),  # 시가
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"현재가 조회 HTTP 오류: {ticker_code} - {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"현재가 조회 오류: {ticker_code} - {e}")
            return None

    async def run(self):
        """
        주기적으로 현재가 조회 및 PriceEvent 발행
        """
        self.is_running = True
        logger.info(
            f"KIS Price Poller 시작 (간격: {self.poll_interval}초, "
            f"종목: {', '.join(self.subscribed_tickers)})"
        )

        try:
            while self.is_running:
                if not self.subscribed_tickers:
                    await asyncio.sleep(self.poll_interval)
                    continue

                # 모든 구독 종목의 현재가 조회
                tasks = [
                    self._fetch_current_price(ticker)
                    for ticker in self.subscribed_tickers
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # PriceEvent 발행
                for result in results:
                    if isinstance(result, dict) and result:
                        try:
                            event = PriceEvent(
                                ticker_code=result["ticker_code"],
                                price=Decimal(result["stck_prpr"]),
                                volume=int(result["acml_vol"]),
                                timestamp=datetime.now(timezone.utc),
                                change=Decimal(result["prdy_vrss"]),
                                change_rate=Decimal(result["prdy_ctrt"]) / 100,
                            )
                            await self.event_bus.publish(event)

                            # 전일대비 부호 처리
                            change_sign = "+" if float(result['prdy_vrss']) >= 0 else ""
                            logger.debug(
                                f"현재가 조회 성공: {result['ticker_code']} = "
                                f"₩{result['stck_prpr']} "
                                f"({change_sign}{result['prdy_vrss']}, {result['prdy_ctrt']}%)"
                            )
                        except Exception as e:
                            logger.error(f"PriceEvent 발행 실패: {e}", exc_info=True)

                # 다음 조회까지 대기
                await asyncio.sleep(self.poll_interval)

        except asyncio.CancelledError:
            logger.info("KIS Price Poller 종료")
            self.is_running = False
            raise
        except Exception as e:
            logger.error(f"KIS Price Poller 오류: {e}", exc_info=True)
            self.is_running = False
            raise

    def stop(self):
        """Poller 중지"""
        self.is_running = False


# 싱글톤 인스턴스
_price_poller: KISPricePoller | None = None


def get_kis_price_poller(poll_interval: float = 2.0) -> KISPricePoller:
    """KIS Price Poller 싱글톤 반환"""
    global _price_poller
    if _price_poller is None:
        _price_poller = KISPricePoller(poll_interval)
    return _price_poller
