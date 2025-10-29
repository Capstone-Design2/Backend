"""
TradingView 관련 공통 도메인 상수
- 프론트엔드와의 계약
- 내부 서비스 간 공통 변환 규칙
"""

# TradingView ↔ 내부 timeframe 매핑
RESOLUTION_TO_TIMEFRAME = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "D": "1D",
}

# 프론트로 노출되는 지원 해상도
SUPPORTED_RESOLUTIONS = list(RESOLUTION_TO_TIMEFRAME.keys())