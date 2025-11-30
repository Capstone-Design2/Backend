# 실시간 모의투자 시스템 구현 계획서

## 📋 개요

본 문서는 한국투자증권 WebSocket API를 활용한 실시간 모의투자(Paper Trading) 시스템의 전체 구현 계획을 담고 있습니다.

---

## 🎯 목표

1. **실시간 시세 스트리밍**: KIS WebSocket을 통한 체결가/호가 실시간 수신
2. **모의투자 주문 실행**: 실시간 시세 기반 매수/매도 시뮬레이션
3. **포지션 관리**: 보유 종목, 잔고, 평가손익 실시간 업데이트
4. **Frontend 연동**: Vue 3 클라이언트에 WebSocket으로 시세 브로드캐스트

---

## 📊 현재 상태 분석

### ✅ 구현 완료
- **KIS REST API 연동**: 인증 토큰 관리 (`kis_auth.py`)
- **일봉/분봉 동기화**: 과거 데이터 수집 API 엔드포인트
- **DB 스키마**: 모의투자 관련 모든 테이블 (accounts, orders, executions, positions, trades)
- **Backtest 시스템**: 전략 백테스팅 기능 완료
- **Frontend**: Vue 3 + Socket.IO Client 설치됨

### ⚠️ 부분 구현
- **WebSocket 인프라**: 라이브러리 설치됨, 서버 로직 없음
- **Approval Key 발급**: `kis_auth.py`에 메서드 존재, 사용처 없음

### ❌ 미구현
- **KIS WebSocket 클라이언트**: 실시간 시세 구독 로직
- **FastAPI WebSocket 서버**: 클라이언트 브로드캐스트 엔드포인트
- **모의투자 비즈니스 로직**: 주문 검증, 체결, 포지션 업데이트
- **API 라우터**: Paper Trading CRUD 엔드포인트
- **Frontend 실시간 연동**: WebSocket 수신 및 UI 업데이트

---

## 🏗️ 아키텍처 설계

### 전체 데이터 플로우

```
[KIS WebSocket Server]
        ↓ (실시간 체결가/호가)
[KIS WebSocket Client] (Backend Background Task)
        ↓ (파싱 & 이벤트 발행)
[PriceEventBus] (메모리 내 큐)
        ↓
┌───────┴──────────┐
│                  │
▼                  ▼
[FastAPI WS]    [Paper Trading Engine]
(브로드캐스트)   (시뮬레이션 체결)
│                  │
▼                  ▼
[Frontend]      [DB: orders/positions/executions]
(차트 업데이트)  (거래 기록 저장)
```

### 주요 컴포넌트

#### 1. **KIS WebSocket Client** (신규 구현)
- **파일**: `Backend/app/services/kis_websocket.py`
- **역할**:
  - KIS WebSocket 서버 연결 (`wss://openapi.koreainvestment.com:9443/tryitout/H0STCNT0`)
  - Approval Key로 인증
  - 종목 구독 메시지 전송 (JSON 형식)
  - 실시간 데이터 파싱 (`|`와 `^`로 구분된 문자열)
  - PriceEventBus에 이벤트 발행
- **구독 TR ID**:
  - `H0STCNT0`: 실시간 체결가
  - `H0STASP0`: 실시간 호가 (선택 구현)

#### 2. **PriceEventBus** (신규 구현)
- **파일**: `Backend/app/core/events.py`
- **역할**:
  - `asyncio.Queue` 기반 이벤트 큐
  - 실시간 시세 이벤트 publish/subscribe 패턴
  - 다중 리스너 지원 (FastAPI WS + Paper Trading Engine)

#### 3. **FastAPI WebSocket Endpoint** (신규 구현)
- **파일**: `Backend/app/routers/websocket.py`
- **엔드포인트**: `/ws/market/{ticker_code}`
- **역할**:
  - 클라이언트 연결 관리 (ConnectionManager)
  - PriceEventBus에서 실시간 데이터 수신
  - 연결된 모든 클라이언트에 브로드캐스트
  - 재연결 처리 및 에러 핸들링

#### 4. **Paper Trading Service** (신규 구현)
- **파일**: `Backend/app/services/paper_trading.py`
- **역할**:
  - 계좌 생성/조회/리셋
  - 주문 검증 (잔고, 보유 수량 체크)
  - 실시간 시세 기반 시뮬레이션 체결
  - 포지션 업데이트 (평균 단가 계산)
  - 평가손익 계산

#### 5. **Order Execution Engine** (신규 구현)
- **파일**: `Backend/app/services/order_executor.py`
- **역할**:
  - PriceEventBus에서 실시간 가격 수신
  - PENDING 상태 주문 조회
  - 체결 조건 확인:
    - `MARKET`: 즉시 체결
    - `LIMIT`: 지정가 도달 시 체결
  - Execution 레코드 생성
  - Order 상태 업데이트 (PENDING → FILLED)
  - Position 업데이트

#### 6. **Paper Trading Router** (신규 구현)
- **파일**: `Backend/app/routers/paper_trading.py`
- **엔드포인트**:
  - `POST /paper-trading/account`: 계좌 개설
  - `GET /paper-trading/account`: 계좌 조회
  - `POST /paper-trading/order`: 주문 제출
  - `GET /paper-trading/orders`: 주문 내역
  - `GET /paper-trading/positions`: 보유 포지션
  - `GET /paper-trading/balance`: 잔고 조회
  - `DELETE /paper-trading/order/{order_id}`: 주문 취소

#### 7. **Frontend WebSocket Integration** (수정)
- **파일**: `Frontend/src/services/websocket.ts`
- **역할**:
  - Socket.IO 클라이언트로 `/ws/market/{ticker}` 연결
  - 실시간 시세 수신 및 `useMarketStore` 업데이트
  - 차트 라이브러리 실시간 갱신
  - 연결 상태 표시 ("준비 중" → "연결됨")

---

## 🔧 기술 스택 및 라이브러리

### Backend
- **WebSocket**: `websockets==14.2` (이미 설치됨)
- **FastAPI WebSocket**: `fastapi.websockets` (내장)
- **비동기 처리**: `asyncio.Queue`, `asyncio.create_task`
- **JSON 파싱**: 표준 `json` 모듈

### Frontend
- **WebSocket Client**: `socket.io-client==4.8.1` (이미 설치됨)
- **상태 관리**: Pinia Store (`useMarketStore`, `usePortfolioStore`)

---

## 📝 구현 단계 (Phase별)

### **Phase 1: KIS WebSocket Client 구현**

#### 1.1. `kis_websocket.py` 생성
- **클래스**: `KISWebSocketClient`
- **메서드**:
  - `async def connect()`: WebSocket 연결 및 Approval Key 인증
  - `async def subscribe(tickers: List[str])`: 종목 구독 메시지 전송
  - `async def _listen()`: 메시지 수신 루프
  - `async def _parse_message(raw: str)`: 파이프/캐럿 파싱
  - `async def disconnect()`: 연결 종료

#### 1.2. 메시지 포맷 구현
- **구독 요청 (JSON)**:
```json
{
  "header": {
    "approval_key": "발급받은키",
    "custtype": "P",
    "tr_type": "1",
    "content-type": "utf-8"
  },
  "body": {
    "input": {
      "tr_id": "H0STCNT0",
      "tr_key": "005930"
    }
  }
}
```

- **응답 파싱 (파이프 구분)**:
```
0|H0STCNT0|001|유가^005930^134511^84600^...
```
  - Split by `|`: `[flag, tr_id, data_cnt, data]`
  - Split data by `^`: 필드 배열

#### 1.3. 백그라운드 태스크 등록
- `main.py` lifespan에 `asyncio.create_task(kis_ws_client.connect())`
- 앱 종료 시 `await kis_ws_client.disconnect()`

---

### **Phase 2: PriceEventBus 구현**

#### 2.1. `core/events.py` 생성
```python
class PriceEvent:
    ticker_code: str
    price: Decimal
    volume: int
    timestamp: datetime

class PriceEventBus:
    _subscribers: List[asyncio.Queue] = []

    async def publish(event: PriceEvent):
        for q in _subscribers:
            await q.put(event)

    def subscribe() -> asyncio.Queue:
        q = asyncio.Queue()
        _subscribers.append(q)
        return q
```

#### 2.2. KIS WebSocket과 연동
- `kis_websocket.py`에서 파싱 완료 후 `PriceEventBus.publish()` 호출

---

### **Phase 3: FastAPI WebSocket Endpoint**

#### 3.1. `routers/websocket.py` 생성
```python
class ConnectionManager:
    active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(ticker: str, ws: WebSocket):
        await ws.accept()
        if ticker not in active_connections:
            active_connections[ticker] = []
        active_connections[ticker].append(ws)

    async def broadcast(ticker: str, message: dict):
        for ws in active_connections.get(ticker, []):
            await ws.send_json(message)

@router.websocket("/ws/market/{ticker_code}")
async def market_websocket(websocket: WebSocket, ticker_code: str):
    await manager.connect(ticker_code, websocket)
    try:
        while True:
            # 클라이언트 메시지 수신 (ping/pong)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ticker_code, websocket)
```

#### 3.2. 백그라운드 브로드캐스터
```python
async def broadcast_worker():
    queue = PriceEventBus.subscribe()
    while True:
        event = await queue.get()
        await manager.broadcast(event.ticker_code, {
            "type": "price",
            "ticker": event.ticker_code,
            "price": float(event.price),
            "volume": event.volume,
            "timestamp": event.timestamp.isoformat()
        })
```
- `main.py` lifespan에 태스크 등록

---

### **Phase 4: Paper Trading Service 구현**

#### 4.1. `services/paper_trading.py` 생성
- **계좌 관리**:
  - `create_account(user_id, initial_balance)`: 중복 방지 (UNIQUE 제약)
  - `get_account(user_id)`: 계좌 조회
  - `reset_account(user_id)`: 잔고/포지션 초기화

- **주문 검증**:
  - `validate_buy(account, ticker, quantity, price)`: 잔고 확인
  - `validate_sell(account, ticker, quantity)`: 보유 수량 확인

- **포지션 계산**:
  - `update_position_on_buy(account, ticker, quantity, price)`: 평균 단가 재계산
  - `update_position_on_sell(account, ticker, quantity, price)`: 수량 차감

#### 4.2. Repository 패턴 적용
- `repositories/paper_trading.py`:
  - `get_account_by_user_id()`
  - `create_order()`
  - `get_pending_orders()`
  - `update_order_status()`
  - `upsert_position()`

---

### **Phase 5: Order Execution Engine**

#### 5.1. `services/order_executor.py` 생성
```python
class OrderExecutor:
    async def run(self):
        price_queue = PriceEventBus.subscribe()
        while True:
            event = await price_queue.get()
            await self._process_price_event(event)

    async def _process_price_event(self, event: PriceEvent):
        # 해당 ticker의 PENDING 주문 조회
        pending = await repo.get_pending_orders_by_ticker(event.ticker_code)

        for order in pending:
            if self._should_fill(order, event.price):
                await self._fill_order(order, event.price)

    def _should_fill(self, order: Order, current_price: Decimal) -> bool:
        if order.order_type == OrderType.MARKET:
            return True
        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                return current_price <= order.limit_price
            else:  # SELL
                return current_price >= order.limit_price
        return False

    async def _fill_order(self, order: Order, price: Decimal):
        # 1. Execution 레코드 생성
        exec_record = Execution(
            order_id=order.order_id,
            quantity=order.quantity,
            price=price,
            exec_time=utc_now()
        )
        await repo.create_execution(exec_record)

        # 2. Order 상태 업데이트
        order.status = OrderStatus.FILLED
        order.completed_at = utc_now()
        await repo.update_order(order)

        # 3. Position 업데이트
        await self._update_position(order, price)

        # 4. Account balance 업데이트
        await self._update_balance(order, price)

    async def _update_position(self, order: Order, price: Decimal):
        position = await repo.get_position(order.account_id, order.ticker_id)

        if order.side == OrderSide.BUY:
            if position:
                # 평균 단가 재계산
                total_cost = position.average_buy_price * position.quantity + price * order.quantity
                total_qty = position.quantity + order.quantity
                position.quantity = total_qty
                position.average_buy_price = total_cost / total_qty
            else:
                # 신규 포지션
                position = Position(
                    account_id=order.account_id,
                    ticker_id=order.ticker_id,
                    quantity=order.quantity,
                    average_buy_price=price
                )
        else:  # SELL
            position.quantity -= order.quantity
            if position.quantity == 0:
                await repo.delete_position(position.position_id)
                return

        await repo.upsert_position(position)

    async def _update_balance(self, order: Order, price: Decimal):
        account = await repo.get_account(order.account_id)

        if order.side == OrderSide.BUY:
            account.current_balance -= price * order.quantity
        else:  # SELL
            account.current_balance += price * order.quantity

        await repo.update_account(account)
```

#### 5.2. 백그라운드 태스크 등록
- `main.py` lifespan에 `asyncio.create_task(order_executor.run())`

---

### **Phase 6: Paper Trading API Router**

#### 6.1. `routers/paper_trading.py` 생성
```python
@router.post("/account")
async def create_account(
    db: AsyncSession,
    current_user: User,
    initial_balance: Decimal = 10_000_000
):
    account = await paper_trading_service.create_account(
        db, current_user.user_id, initial_balance
    )
    return {"account_id": account.account_id}

@router.get("/account")
async def get_account(db: AsyncSession, current_user: User):
    account = await paper_trading_service.get_account(db, current_user.user_id)
    return account

@router.post("/order")
async def submit_order(
    db: AsyncSession,
    current_user: User,
    ticker_code: str,
    side: OrderSide,
    quantity: Decimal,
    order_type: OrderType = OrderType.MARKET,
    limit_price: Optional[Decimal] = None
):
    order = await paper_trading_service.submit_order(
        db,
        user_id=current_user.user_id,
        ticker_code=ticker_code,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price
    )
    return {"order_id": order.order_id, "status": order.status}

@router.get("/positions")
async def get_positions(db: AsyncSession, current_user: User):
    positions = await paper_trading_service.get_positions(db, current_user.user_id)
    return positions

@router.get("/balance")
async def get_balance(db: AsyncSession, current_user: User):
    balance = await paper_trading_service.get_balance(db, current_user.user_id)
    return balance
```

#### 6.2. `main.py`에 라우터 등록
```python
from app.routers import paper_trading_router
app.include_router(paper_trading_router)
```

---

### **Phase 7: Frontend Integration**

#### 7.1. `services/websocket.ts` 생성
```typescript
import { io, Socket } from 'socket.io-client'
import { useMarketStore } from '@/stores/useMarketStore'

let socket: Socket | null = null

export function connectMarketWebSocket(ticker: string) {
  if (socket) socket.disconnect()

  socket = io(`ws://localhost:8000/ws/market/${ticker}`, {
    transports: ['websocket']
  })

  socket.on('connect', () => {
    console.log('WebSocket connected')
  })

  socket.on('message', (data: any) => {
    if (data.type === 'price') {
      const marketStore = useMarketStore()
      marketStore.updateLivePrice(data.price)
      // 차트 업데이트 로직
    }
  })

  socket.on('disconnect', () => {
    console.log('WebSocket disconnected')
  })
}

export function disconnectMarketWebSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}
```

#### 7.2. `DashboardView.vue` 수정
```vue
<script setup>
import { onMounted, onUnmounted } from 'vue'
import { connectMarketWebSocket, disconnectMarketWebSocket } from '@/services/websocket'

onMounted(() => {
  connectMarketWebSocket('005930')
})

onUnmounted(() => {
  disconnectMarketWebSocket()
})
</script>

<template>
  <p class="text-sm text-slate-400">
    데이터: 한국투자증권 · WebSocket: {{ wsStatus }}
  </p>
</template>
```

#### 7.3. `useMarketStore.ts` 수정
```typescript
export const useMarketStore = defineStore('market', {
  state: () => ({
    livePrice: null as number | null,
    wsConnected: false
  }),
  actions: {
    updateLivePrice(price: number) {
      this.livePrice = price
    },
    setWsStatus(connected: boolean) {
      this.wsConnected = connected
    }
  }
})
```

#### 7.4. `TradeWidget.vue` 수정
- 기존 `executeBuy/Sell` 로직 제거
- API 호출로 변경:
```typescript
async function handleTrade(type: 'buy' | 'sell') {
  const response = await axios.post('/api/paper-trading/order', {
    ticker_code: symbol.value,
    side: type.toUpperCase(),
    quantity: quantity.value,
    order_type: 'MARKET'
  })

  uiStore.pushToast({
    type: 'success',
    message: `Order submitted: ${response.data.order_id}`
  })
}
```

---

## 🔐 보안 및 예외 처리

### 1. **WebSocket 인증**
- JWT 토큰 기반 클라이언트 인증 (선택 구현)
- Approval Key 만료 시 자동 재발급

### 2. **에러 핸들링**
- KIS WebSocket 연결 끊김 → 자동 재연결 (exponential backoff)
- FastAPI WebSocket 클라이언트 연결 끊김 → ConnectionManager에서 제거
- 주문 검증 실패 → 400 에러 반환 및 롤백

### 3. **Race Condition 방지**
- Position 업데이트 시 DB Row Lock (`SELECT ... FOR UPDATE`)
- Order 상태 변경 시 Optimistic Locking 또는 트랜잭션 격리 레벨 상향

### 4. **Rate Limiting**
- KIS API 호출 제한 준수 (초당 5건, 분당 100건)
- WebSocket 구독 제한 (최대 20종목)

---

## 📈 성능 최적화

### 1. **메모리 관리**
- PriceEventBus Queue 크기 제한 (maxsize=1000)
- 오래된 체결 데이터 자동 삭제

### 2. **DB 쿼리 최적화**
- Position 조회 시 인덱스 활용 (`account_id, ticker_id`)
- Batch Insert for Executions

### 3. **WebSocket 메시지 압축**
- JSON 페이로드 최소화 (필수 필드만 전송)

---

## 🧪 테스트 계획

### 1. **Unit Tests**
- `kis_websocket.py`: 메시지 파싱 로직
- `order_executor.py`: 체결 조건 검증
- `paper_trading.py`: 포지션 계산 로직

### 2. **Integration Tests**
- KIS WebSocket → PriceEventBus → Order Execution 전체 플로우
- REST API → DB 저장 → 조회 검증

### 3. **Load Tests**
- 1000개 주문 동시 처리
- 100명 동시 WebSocket 연결

---

## 📅 구현 일정 (예상)

| Phase | 작업 내용 | 파일 수 | 예상 시간 |
|-------|----------|---------|----------|
| Phase 1 | KIS WebSocket Client | 1 | 4시간 |
| Phase 2 | PriceEventBus | 1 | 2시간 |
| Phase 3 | FastAPI WebSocket Endpoint | 1 | 3시간 |
| Phase 4 | Paper Trading Service + Repository | 2 | 5시간 |
| Phase 5 | Order Execution Engine | 1 | 4시간 |
| Phase 6 | Paper Trading API Router | 1 | 3시간 |
| Phase 7 | Frontend Integration | 3 | 4시간 |
| **합계** | | **10개 파일** | **25시간** |

---

## 🚀 배포 고려사항

### 1. **환경 변수**
- `.env`에 WebSocket URL 추가:
```
KIS_WS_URL=wss://openapi.koreainvestment.com:9443
KIS_WS_PATH=/tryitout/H0STCNT0
```

### 2. **프로세스 관리**
- Uvicorn worker 수 조정 (WebSocket은 단일 프로세스 권장)
- 백그라운드 태스크 헬스체크

### 3. **모니터링**
- WebSocket 연결 상태 로깅
- 주문 체결 지연 메트릭
- PriceEventBus 큐 크기 모니터링

---

## 📚 참고 자료

### 공식 문서
- [KIS Developers - 한국투자증권 오픈API 개발자센터](https://apiportal.koreainvestment.com/intro)
- [GitHub - Korea Investment Open Trading API](https://github.com/koreainvestment/open-trading-api)

### WebSocket 구현 예제
- [WikiDocs - 파이썬으로 배우는 한국투자증권 WebSocket](https://wikidocs.net/book/7847)
- [WikiDocs - 코드 설명](https://wikidocs.net/170517)
- [Velog - JAVA 한국투자증권 OpenAPI WebSocket](https://velog.io/@seon7129/JAVA-한국투자증권-OpenAPI-사용-Websocket)

### 기술 문서
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Socket.IO Client (Vue)](https://socket.io/docs/v4/client-api/)

---

## ✅ 체크리스트

구현 전 확인 사항:

- [ ] KIS API 계정 활성화 및 Approval Key 발급 가능 여부
- [ ] `websockets` 라이브러리 설치 확인
- [ ] DB 마이그레이션 완료 (paper_trading 테이블)
- [ ] Frontend `socket.io-client` 설치 확인
- [ ] 개발 환경 CORS 설정 (WebSocket origin 허용)

---

## 🎯 핵심 구현 포인트

1. **KIS WebSocket 메시지 파싱**
   - 파이프(`|`)와 캐럿(`^`)으로 구분된 문자열 처리
   - TR ID별 필드 순서 매핑 (H0STCNT0는 30개 필드)

2. **비동기 이벤트 처리**
   - `asyncio.Queue`로 pub/sub 패턴 구현
   - 백그라운드 태스크 간 데이터 전달

3. **원자성 보장**
   - 주문 체결 시 DB 트랜잭션 사용
   - Position 업데이트 시 동시성 제어

4. **실시간 브로드캐스트**
   - FastAPI WebSocket으로 다중 클라이언트 관리
   - 종목별 구독 관리 (ConnectionManager)

---

## 🔄 향후 확장 가능성

### Phase 8 (추가 기능)
- **실시간 호가**: `H0STASP0` TR ID 구독
- **주문 체결 통보**: `H0STCNI0/H0STCNI9` 구독
- **Stop Loss/Take Profit**: 자동 손절/익절 주문
- **포트폴리오 분석**: 샤프 비율, MDD 계산
- **전략 자동 실행**: Backtest 전략을 실시간 적용
- **알림 시스템**: 주문 체결 시 Frontend 알림

---

## 📌 결론

본 계획서는 **25시간** 분량의 실시간 모의투자 시스템 구현 로드맵을 제시합니다.

핵심은:
1. **KIS WebSocket** ↔ **PriceEventBus** ↔ **Order Executor** 파이프라인 구축
2. **FastAPI WebSocket**으로 Frontend 실시간 연동
3. **DB 트랜잭션**으로 주문 체결 원자성 보장

각 Phase는 독립적으로 테스트 가능하며, 순차적으로 구현 시 최종적으로 완전한 실시간 Paper Trading 시스템이 완성됩니다.

---

**작성일**: 2025-11-30
**작성자**: Claude (Plan Mode)
