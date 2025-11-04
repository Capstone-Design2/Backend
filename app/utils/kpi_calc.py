# app/services/kpi_service.py
from __future__ import annotations
import math
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd

class KpiCalc:
    """
    equity_curve: 시계열 에쿼티(잔고) Series (DatetimeIndex 권장)
    trades: [{"timestamp": ..., "price": ..., "side": "buy"|"sell"}, ...]
    initial_balance: 초기 자본금
    """
    def __init__(
        self,
        equity_curve: pd.Series,
        trades: List[Dict[str, Any]],
        initial_balance: float,
        risk_free_rate_annual: float = 0.0,   # 연간 무위험수익률 (예: 0.02 = 2%)
        infer_frequency: bool = True,         # 인덱스 빈도 추정하여 연율화 스케일 자동 적용
    ):
        self.equity_curve = equity_curve.astype(float)
        self.trades = trades or []
        self.initial_balance = float(initial_balance)
        self.risk_free_rate_annual = float(risk_free_rate_annual)
        self.infer_frequency = infer_frequency

    # ---------- public ----------
    def calculate_kpis(self) -> Dict[str, Any]:
        if self.equity_curve is None or len(self.equity_curve.dropna()) < 2:
            return {
                "total_return": 0.0, "cagr": 0.0, "sharpe": 0.0,
                "sortino": 0.0, "vol_annual": 0.0,
                "max_drawdown": 0.0, "max_dd_start": None, "max_dd_end": None, "max_dd_duration_days": 0,
                "calmar": 0.0,
                "num_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0,
            }

        s = self.equity_curve.dropna().copy()
        # 인덱스 정렬 및 중복 제거
        s = s[~s.index.duplicated(keep="last")].sort_index()

        # 빈도/연율화 스케일 추정
        periods_per_year = self._infer_periods_per_year(s) if self.infer_frequency else 252.0
        scale = math.sqrt(periods_per_year)

        # 수익률 계산
        rets = s.pct_change().dropna()
        if rets.empty:
            return self._zero_like()

        # 총수익률 & 기간
        total_return = float(s.iloc[-1] / self.initial_balance - 1.0)
        years = max((s.index[-1] - s.index[0]).days / 365.25, 0.0)
        cagr = self._safe_cagr(total_return, years)

        # 무위험수익률을 주기 단위로 변환
        rf_per_period = (1 + self.risk_free_rate_annual) ** (1 / periods_per_year) - 1
        excess = rets - rf_per_period

        # 변동성/Sharpe/Sortino
        vol_ann = float(rets.std(ddof=1) * scale) if len(rets) > 1 else 0.0
        sharpe = float(excess.mean() / excess.std(ddof=1) * scale) if len(excess) > 1 and excess.std(ddof=1) > 0 else 0.0

        downside = rets.copy()
        downside[downsides_mask := (downsides := rets < 0)]  # noqa: visual hint
        downside = rets[rets < 0]
        downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
        sortino = float((rets.mean() - rf_per_period) / downside_std * scale) if downside_std > 0 else 0.0

        # 드로우다운
        mdd, dd_start, dd_end, dd_duration = self._max_drawdown_stats(s)

        # Calmar (연간수익률 / |MDD|)
        calmar = float(cagr / abs(mdd)) if mdd < 0 else 0.0

        # 거래 통계(간단 버전: 연속 페어링)
        trade_stats = self._compute_trade_stats(self.trades)

        return {
            "total_return": total_return,
            "cagr": cagr,
            "sharpe": sharpe,
            "sortino": sortino,
            "vol_annual": vol_ann,
            "max_drawdown": mdd,
            "max_dd_start": dd_start,
            "max_dd_end": dd_end,
            "max_dd_duration_days": dd_duration,
            "calmar": calmar,
            **trade_stats,
        }

    # ---------- helpers ----------
    def _zero_like(self) -> Dict[str, Any]:
        return {
            "total_return": 0.0, "cagr": 0.0, "sharpe": 0.0, "sortino": 0.0, "vol_annual": 0.0,
            "max_drawdown": 0.0, "max_dd_start": None, "max_dd_end": None, "max_dd_duration_days": 0,
            "calmar": 0.0, "num_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0,
        }

    def _infer_periods_per_year(self, s: pd.Series) -> float:
        """인덱스 간격으로 관측 빈도를 추정하여 연율화 스케일을 결정(일:252, 시간: ~24*252, 분: ~390*252 등)."""
        idx = s.index
        if not isinstance(idx, pd.DatetimeIndex) or len(idx) < 2:
            return 252.0
        # 평균 간격
        deltas = (idx[1:] - idx[:-1]).to_series(index=idx[1:]).dt.total_seconds().dropna()
        if deltas.empty:
            return 252.0
        sec = float(deltas.median())
        # 간단 맵핑
        if sec >= 24 * 3600 * 0.75:   # ~1일
            return 252.0
        if sec >= 3600 * 0.75:        # ~1시간
            return 252.0 * 24.0
        if sec >= 60 * 0.75:          # ~1분
            # 미국 주식 기준 거래 분(6.5시간*60=390) 근사
            return 252.0 * 390.0
        # 초 단위 등 고빈도는 보수적으로 가정
        return 252.0 * 24.0 * 60.0

    def _safe_cagr(self, total_return: float, years: float) -> float:
        """연수가 0이거나 총손실이 100% 이하(=자본 0)인 경우 NaN 방지."""
        if years <= 0 or total_return <= -1.0:
            return 0.0
        try:
            return float((1.0 + total_return) ** (1.0 / years) - 1.0)
        except Exception:
            return 0.0

    def _max_drawdown_stats(self, equity: pd.Series) -> Tuple[float, Optional[pd.Timestamp], Optional[pd.Timestamp], int]:
        roll_max = equity.cummax()
        dd = equity / roll_max - 1.0
        # 최대 낙폭
        mdd = float(dd.min())
        # 기간(시작/끝) 추정
        end_idx = dd.idxmin()
        # 고점 시점(롤링 최대치가 기록된 가장 최근 시점)
        peak_idx = equity.loc[:end_idx].idxmax()
        duration = (end_idx - peak_idx).days if isinstance(end_idx, pd.Timestamp) else 0
        return mdd, peak_idx, end_idx, int(max(duration, 0))

    def _compute_trade_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        매우 단순한 페어링: buy→sell 또는 sell→buy 순으로 짝지어 P/L을 계산.
        백테스트에서 포지션 사이징/수수료가 없다면 참고치로 충분.
        """
        if not trades or len(trades) < 2:
            return {"num_trades": len(trades or []), "win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0}

        # 정렬
        df = pd.DataFrame(trades)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.sort_values("timestamp").reset_index(drop=True)

        # 롱/숏 구분하여 P/L 계산(1 계약 가정)
        pnl_list = []
        i = 0
        while i + 1 < len(df):
            a, b = df.iloc[i], df.iloc[i + 1]
            if a["side"] == "buy" and b["side"] == "sell":
                pnl = float(b["price"] - a["price"])
            elif a["side"] == "sell" and b["side"] == "buy":
                pnl = float(a["price"] - b["price"])
            else:
                i += 1
                continue
            pnl_list.append(pnl)
            i += 2

        if not pnl_list:
            return {"num_trades": len(trades), "win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0}

        pnl = np.array(pnl_list, dtype=float)
        wins = pnl[pnl > 0]
        losses = -pnl[pnl < 0]

        num = len(pnl_list)
        win_rate = float(len(wins) / num) if num > 0 else 0.0
        gross_win = float(wins.sum()) if wins.size else 0.0
        gross_loss = float(losses.sum()) if losses.size else 0.0
        profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
        expectancy = float(pnl.mean()) if num > 0 else 0.0

        return {
            "num_trades": num,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
        }
