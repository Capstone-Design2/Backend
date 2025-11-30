"""
FastAPI WebSocket Endpoint
클라이언트에게 실시간 시세 데이터 브로드캐스트
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from app.core.events import get_price_event_bus, PriceEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """
    WebSocket 연결 관리
    종목별로 클라이언트 그룹 관리
    """

    def __init__(self):
        # ticker_code -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ticker_code: str, websocket: WebSocket) -> None:
        """
        클라이언트 연결 등록

        Args:
            ticker_code: 종목 코드
            websocket: WebSocket 연결
        """
        await websocket.accept()

        async with self._lock:
            if ticker_code not in self.active_connections:
                self.active_connections[ticker_code] = []
            self.active_connections[ticker_code].append(websocket)

        logger.info(
            f"WebSocket 연결: {ticker_code} "
            f"(총 {len(self.active_connections[ticker_code])}명 구독)"
        )

    async def disconnect(self, ticker_code: str, websocket: WebSocket) -> None:
        """
        클라이언트 연결 해제

        Args:
            ticker_code: 종목 코드
            websocket: WebSocket 연결
        """
        async with self._lock:
            if ticker_code in self.active_connections:
                if websocket in self.active_connections[ticker_code]:
                    self.active_connections[ticker_code].remove(websocket)

                # 빈 리스트 제거
                if not self.active_connections[ticker_code]:
                    del self.active_connections[ticker_code]

        logger.info(
            f"WebSocket 연결 해제: {ticker_code} "
            f"(남은 구독자: {len(self.active_connections.get(ticker_code, []))}명)"
        )

    async def broadcast(self, ticker_code: str, message: dict) -> None:
        """
        특정 종목을 구독 중인 모든 클라이언트에게 메시지 전송

        Args:
            ticker_code: 종목 코드
            message: 전송할 메시지 (dict)
        """
        if ticker_code not in self.active_connections:
            return

        # 연결 끊긴 클라이언트 수집
        disconnected = []

        for websocket in self.active_connections[ticker_code]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"메시지 전송 실패: {e}")
                disconnected.append(websocket)

        # 연결 끊긴 클라이언트 제거
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if ws in self.active_connections[ticker_code]:
                        self.active_connections[ticker_code].remove(ws)

    def get_connection_count(self, ticker_code: str) -> int:
        """특정 종목의 구독자 수 반환"""
        return len(self.active_connections.get(ticker_code, []))

    def get_total_connections(self) -> int:
        """전체 연결 수 반환"""
        return sum(len(conns) for conns in self.active_connections.values())


# 싱글톤 인스턴스
manager = ConnectionManager()


@router.websocket("/market/{ticker_code}")
async def market_websocket(websocket: WebSocket, ticker_code: str):
    """
    실시간 시세 WebSocket 엔드포인트

    Args:
        ticker_code: 종목 코드 (예: 005930)

    Protocol:
        - Client → Server: ping (keep-alive)
        - Server → Client: JSON 메시지
          {
            "type": "price",
            "ticker_code": "005930",
            "price": 84600,
            "volume": 1234,
            "timestamp": "2025-11-30T12:34:56Z",
            "change": -400,
            "change_rate": -0.47
          }
    """
    await manager.connect(ticker_code, websocket)

    try:
        # 클라이언트 메시지 수신 루프 (ping/pong)
        while True:
            try:
                # 클라이언트가 보낸 메시지 수신 (타임아웃 60초)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                logger.debug(f"클라이언트 메시지 수신: {data}")

            except asyncio.TimeoutError:
                # 타임아웃 시 연결 유지 확인
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info(f"클라이언트 연결 종료: {ticker_code}")
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}", exc_info=True)
    finally:
        await manager.disconnect(ticker_code, websocket)


async def broadcast_worker():
    """
    PriceEventBus에서 이벤트를 수신하여 WebSocket 클라이언트에게 브로드캐스트

    백그라운드 태스크로 실행됨 (main.py lifespan)
    """
    event_bus = get_price_event_bus()
    queue = event_bus.subscribe()

    logger.info("WebSocket 브로드캐스트 워커 시작")

    try:
        while True:
            # 이벤트 수신 대기
            event: PriceEvent = await queue.get()

            # JSON 메시지 생성
            message = {
                "type": "price",
                "ticker_code": event.ticker_code,
                "price": float(event.price),
                "volume": event.volume,
                "timestamp": event.timestamp.isoformat(),
                "change": float(event.change),
                "change_rate": float(event.change_rate),
            }

            # 해당 종목 구독자에게 브로드캐스트
            await manager.broadcast(event.ticker_code, message)

    except asyncio.CancelledError:
        logger.info("WebSocket 브로드캐스트 워커 종료")
        event_bus.unsubscribe(queue)
    except Exception as e:
        logger.error(f"브로드캐스트 워커 오류: {e}", exc_info=True)
