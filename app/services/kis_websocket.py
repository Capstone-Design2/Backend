"""
KIS (한국투자증권) WebSocket Client
실시간 시세 데이터 수신 및 파싱
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.services.kis_auth import get_kis_auth_manager, KIS_DOMAIN
from app.core.events import get_price_event_bus, PriceEvent

logger = logging.getLogger(__name__)

# KIS WebSocket URL - 포트 번호 제거 필요 (표준 포트 443 사용)
_ws_url = KIS_DOMAIN.replace("https://", "wss://").replace("http://", "ws://")
KIS_WS_URL = _ws_url.replace(":9443", "")  # 포트 번호 제거


class PriceData:
    """실시간 체결가 데이터"""
    def __init__(
        self,
        ticker_code: str,
        price: Decimal,
        volume: int,
        timestamp: datetime,
        change: Decimal = Decimal("0"),
        change_rate: Decimal = Decimal("0"),
    ):
        self.ticker_code = ticker_code
        self.price = price
        self.volume = volume
        self.timestamp = timestamp
        self.change = change
        self.change_rate = change_rate

    def __repr__(self):
        return (
            f"PriceData(ticker={self.ticker_code}, price={self.price}, "
            f"volume={self.volume}, time={self.timestamp})"
        )


class KISWebSocketClient:
    """
    한국투자증권 WebSocket 클라이언트
    실시간 체결가(H0STCNT0) 구독 및 파싱
    """

    def __init__(self):
        self.auth_manager = get_kis_auth_manager()
        self.event_bus = get_price_event_bus()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.subscribed_tickers: List[str] = []
        self.approval_key: Optional[str] = None

        # 재연결 설정
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.current_retry = 0

    async def connect(self) -> None:
        """WebSocket 연결 및 인증"""
        logger.info("KIS WebSocket 연결 시작...")

        try:
            # Approval Key 발급
            self.approval_key = await self.auth_manager.get_approval_key()
            logger.info(f"Approval Key 발급 완료: {self.approval_key[:10]}...")

            # WebSocket 연결
            ws_url = f"{KIS_WS_URL}/tryitout/H0STCNT0"

            # SSL 검증 비활성화 (모의투자 서버의 인증서 문제 회피)
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10,
                ssl=ssl_context
            )
            self.is_connected = True
            self.current_retry = 0

            logger.info(f"KIS WebSocket 연결 성공: {ws_url}")

        except Exception as e:
            logger.error(f"KIS WebSocket 연결 실패: {e}")
            raise

    async def subscribe(self, tickers: List[str]) -> None:
        """
        종목 구독 메시지 전송

        Args:
            tickers: 종목 코드 리스트 (예: ['005930', '000660'])
        """
        if not self.is_connected or not self.ws:
            raise RuntimeError("WebSocket이 연결되지 않았습니다. connect()를 먼저 호출하세요.")

        for ticker in tickers:
            if ticker in self.subscribed_tickers:
                logger.debug(f"이미 구독 중인 종목: {ticker}")
                continue

            # 구독 요청 메시지 (JSON 형식)
            subscribe_msg = {
                "header": {
                    "approval_key": self.approval_key,
                    "custtype": "P",  # 개인
                    "tr_type": "1",   # 구독 등록
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",  # 실시간 체결가
                        "tr_key": ticker
                    }
                }
            }

            try:
                await self.ws.send(json.dumps(subscribe_msg))
                self.subscribed_tickers.append(ticker)
                logger.info(f"종목 구독 완료: {ticker}")
            except Exception as e:
                logger.error(f"종목 구독 실패 ({ticker}): {e}")

    async def unsubscribe(self, tickers: List[str]) -> None:
        """
        종목 구독 해제

        Args:
            tickers: 종목 코드 리스트
        """
        if not self.is_connected or not self.ws:
            logger.warning("WebSocket이 연결되지 않아 구독 해제를 건너뜁니다.")
            return

        for ticker in tickers:
            if ticker not in self.subscribed_tickers:
                continue

            unsubscribe_msg = {
                "header": {
                    "approval_key": self.approval_key,
                    "custtype": "P",
                    "tr_type": "2",   # 구독 해제
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",
                        "tr_key": ticker
                    }
                }
            }

            try:
                await self.ws.send(json.dumps(unsubscribe_msg))
                self.subscribed_tickers.remove(ticker)
                logger.info(f"종목 구독 해제: {ticker}")
            except Exception as e:
                logger.error(f"종목 구독 해제 실패 ({ticker}): {e}")

    async def listen(self) -> None:
        """
        WebSocket 메시지 수신 루프
        연결이 끊기면 자동 재연결 시도
        """
        while True:
            try:
                if not self.is_connected:
                    await self._reconnect()

                if not self.ws:
                    await asyncio.sleep(1)
                    continue

                # 메시지 수신
                raw_message = await self.ws.recv()
                await self._handle_message(raw_message)

            except ConnectionClosed as e:
                logger.warning(f"WebSocket 연결 종료: {e}")
                self.is_connected = False
                await self._reconnect()

            except WebSocketException as e:
                logger.error(f"WebSocket 오류: {e}")
                self.is_connected = False
                await self._reconnect()

            except Exception as e:
                logger.error(f"메시지 처리 중 예외 발생: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _handle_message(self, raw: str) -> None:
        """
        수신한 메시지 파싱 및 처리

        메시지 포맷: "0|H0STCNT0|001|유가^005930^134511^84600^..."
        - 파이프(|)로 구분: [flag, tr_id, data_cnt, data]
        - 데이터는 캐럿(^)으로 구분된 필드 배열
        """
        try:
            # 파이프로 분리
            parts = raw.split("|")

            if len(parts) < 4:
                logger.debug(f"알 수 없는 메시지 포맷: {raw[:100]}")
                return

            _, tr_id, _, data = parts[0], parts[1], parts[2], parts[3]

            # 실시간 체결가 데이터 확인
            if tr_id != "H0STCNT0":
                logger.debug(f"처리하지 않는 TR_ID: {tr_id}")
                return

            # 데이터 파싱
            price_data = self._parse_h0stcnt0(data)

            if price_data:
                # PriceEventBus로 이벤트 발행
                event = PriceEvent(
                    ticker_code=price_data.ticker_code,
                    price=price_data.price,
                    volume=price_data.volume,
                    timestamp=price_data.timestamp,
                    change=price_data.change,
                    change_rate=price_data.change_rate,
                )
                await self.event_bus.publish(event)

        except Exception as e:
            logger.error(f"메시지 파싱 실패: {e}, 원본: {raw[:200]}", exc_info=True)

    def _parse_h0stcnt0(self, data: str) -> Optional[PriceData]:
        """
        H0STCNT0 (실시간 체결가) 데이터 파싱

        필드 순서 (캐럿 구분, 총 30개 필드):
        0: 유가/코스닥 구분
        1: 종목코드 (6자리)
        2: 체결시간 (HHMMSS)
        3: 현재가
        4: 전일대비 부호
        5: 전일대비
        6: 전일대비율
        7: 가중평균가격
        8: 시가
        9: 고가
        10: 저가
        11: 매도호가1
        12: 매수호가1
        13: 체결거래량
        14: 누적거래량
        15: 누적거래대금
        ...
        """
        try:
            fields = data.split("^")

            if len(fields) < 15:
                logger.warning(f"필드 수 부족 (expected >= 15, got {len(fields)})")
                return None

            ticker_code = fields[1].strip()
            time_str = fields[2].strip()  # HHMMSS
            current_price = Decimal(fields[3].strip())
            change_sign = fields[4].strip()  # 1:상한, 2:상승, 3:보합, 4:하한, 5:하락
            change_value = Decimal(fields[5].strip())
            change_rate = Decimal(fields[6].strip())
            volume_str = fields[13].strip()

            # 거래량 파싱 (빈 값 처리)
            volume = int(volume_str) if volume_str else 0

            # 전일대비 부호 처리
            if change_sign in ("4", "5"):  # 하한, 하락
                change_value = -change_value
                change_rate = -change_rate

            # 타임스탬프 생성 (현재 날짜 + 체결시간)
            now = datetime.now(timezone.utc)
            hour = int(time_str[0:2])
            minute = int(time_str[2:4])
            second = int(time_str[4:6])
            timestamp = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

            return PriceData(
                ticker_code=ticker_code,
                price=current_price,
                volume=volume,
                timestamp=timestamp,
                change=change_value,
                change_rate=change_rate,
            )

        except Exception as e:
            logger.error(f"H0STCNT0 파싱 오류: {e}, 데이터: {data[:200]}")
            return None

    async def _reconnect(self) -> None:
        """
        WebSocket 재연결 (exponential backoff)
        """
        if self.current_retry >= self.max_retries:
            logger.error(f"최대 재연결 시도 횟수 초과 ({self.max_retries}). 재연결을 중단합니다.")
            return

        self.current_retry += 1
        delay = self.retry_delay * (2 ** (self.current_retry - 1))  # 지수 백오프

        logger.info(f"WebSocket 재연결 시도 {self.current_retry}/{self.max_retries} (대기: {delay}초)")
        await asyncio.sleep(delay)

        try:
            await self.connect()

            # 기존 구독 종목 재구독
            if self.subscribed_tickers:
                logger.info(f"재연결 후 종목 재구독: {self.subscribed_tickers}")
                tickers_to_resubscribe = self.subscribed_tickers.copy()
                self.subscribed_tickers.clear()
                await self.subscribe(tickers_to_resubscribe)

        except Exception as e:
            logger.error(f"재연결 실패: {e}")

    async def disconnect(self) -> None:
        """WebSocket 연결 종료"""
        if self.ws and self.is_connected:
            try:
                # 모든 구독 해제
                if self.subscribed_tickers:
                    await self.unsubscribe(self.subscribed_tickers.copy())

                await self.ws.close()
                logger.info("KIS WebSocket 연결 종료")
            except Exception as e:
                logger.error(f"WebSocket 종료 중 오류: {e}")
            finally:
                self.is_connected = False
                self.ws = None


# 싱글톤 인스턴스
_kis_ws_client: Optional[KISWebSocketClient] = None


def get_kis_ws_client() -> KISWebSocketClient:
    """KIS WebSocket Client 싱글톤 반환"""
    global _kis_ws_client
    if _kis_ws_client is None:
        _kis_ws_client = KISWebSocketClient()
    return _kis_ws_client
