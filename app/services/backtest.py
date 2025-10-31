# app/services/backtest.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta

from app.services.kpi_service import KpiService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trade:
    timestamp: pd.Timestamp
    price: float
    side: str  # "buy" | "sell"


class BacktestService:
    """
    단일 종목 시계열에 대해 (룰 기반) 백테스트를 수행합니다.

    입력
    - strategy: Dict (indicators/derived/rules 스키마)
    - data:     pd.DataFrame: columns ⊇ ["timestamp","open","high","low","close","volume"]

    출력 (self.run)
    - Dict[str, Any]:
        {
          "trades": List[Dict[str,Any]],
          "equity_curve": List[{"timestamp": ..., "equity": ...}],
          ... (KpiService.calculate_kpis() 결과 포함)
        }
    """
    def __init__(self, strategy: Dict[str, Any], data: pd.DataFrame):
        self.strategy = strategy or {}
        self.data = data.copy()
        self.results: Dict[str, Any] = {}
        self.initial_balance: float = float(1_000_000)

    # ---------- public ----------
    def run(self) -> Dict[str, Any]:
        if not isinstance(self.data, pd.DataFrame) or len(self.data) < 2:
            return {"error": "Not enough data to run backtest"}

        self._prep_dataframe()

        # 지표 요구사항을 rules/derived에서 추론 → 누락분 계산 → 명시분 계산
        needed = self._infer_needed_indicators_from_rules_and_derived()
        self._compute_missing_inferred_indicators(needed)
        self._calculate_indicators()  # 명시된 indicators/derived 처리

        # 거래 실행 및 성과 계산
        self._execute_trades()
        self._calculate_metrics()
        return self.results

    # ---------- basic prep ----------
    def _prep_dataframe(self) -> None:
        """타임스탬프 정렬, 수치형 캐스팅 등 공통 전처리."""
        if "timestamp" in self.data.columns:
            self.data["timestamp"] = pd.to_datetime(self.data["timestamp"], errors="coerce")
            self.data = self.data.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        else:
            raise ValueError("Input data must contain 'timestamp' column")

        for c in ("open", "high", "low", "close", "volume"):
            if c in self.data.columns:
                self.data[c] = pd.to_numeric(self.data[c], errors="coerce")

        # 혹시 존재한다면 이전 결과 컬럼 제거(깨끗한 상태 보장)
        for col in ("signal", "position", "equity"):
            if col in self.data.columns:
                self.data.drop(columns=[col], inplace=True)

    # ---------- indicators & derived ----------
    def _calculate_indicators(self) -> None:
        """
        1) indicators 섹션 계산 (EMA, BBANDS 등)
        2) derived 섹션 계산 (수식/shift 지원, 점(.) 포함 컬럼명 안전 평가)
        """
        # 1) 기본 지표
        for ind in self.strategy.get("indicators", []) or []:
            t = (ind.get("type") or "").lower()
            k = ind.get("key")
            p = ind.get("params", {}) or {}

            if not k:
                logger.debug("Indicator without key skipped: %s", ind)
                continue

            try:
                if t == "ema":
                    self.data[k] = ta.ema(self.data["close"], length=int(p.get("length", 20)))

                elif t in {"bollinger_bands", "bbands", "bb"}:
                    length = int(p.get("length", 20))
                    std = float(p.get("stddev", p.get("std", 2)))
                    self._compute_bbands(length, std, key_prefix=k)

                elif t == "sma":
                    self.data[k] = ta.sma(self.data["close"], length=int(p.get("length", 20)))

                else:
                    logger.warning("Unknown indicator type: %s", t)
            except Exception as e:
                logger.exception("Failed to compute indicator %s (%s): %s", k, t, e)

        # 2) 파생 지표
        for drv in self.strategy.get("derived", []) or []:
            key = drv.get("key")
            formula = drv.get("formula")
            if not key or not formula:
                continue
            try:
                series = self._eval_derived_formula_safe(formula)
                self.data[key] = series
                logger.debug("Derived column computed: %s", key)
            except Exception as e:
                logger.exception("Failed to compute derived column '%s': %s", key, e)

    def _compute_bbands(self, length: int, std: float, key_prefix: Optional[str] = None) -> None:
        """
        pandas-ta 버전별 컬럼명이 조금씩 다른 이슈를 보완하여
        lower/middle/upper를 안정적으로 추출합니다.
        """
        bb = ta.bbands(self.data["close"], length=length, std=std)
        # 버전에 따라 "BBL_", "BBM_", "BBU_" 접두, 혹은 BBL, BBM, BBU 혼재 → 안전 매핑
        def _first_col(prefix: str) -> Optional[str]:
            return next((c for c in bb.columns if str(c).startswith(prefix)), None)

        lower_col = _first_col("BBL_") or _first_col("BBL")
        middle_col = _first_col("BBM_") or _first_col("BBM")
        upper_col = _first_col("BBU_") or _first_col("BBU")

        if not (lower_col and middle_col and upper_col):
            raise RuntimeError(f"Unexpected BBANDS columns: {list(bb.columns)}")

        def _out_name(suffix: str) -> str:
            if key_prefix:
                return f"{key_prefix}.{suffix}"
            return f"bb.{length}.{suffix}"

        self.data[_out_name("lower")] = bb[lower_col]
        self.data[_out_name("middle")] = bb[middle_col]
        self.data[_out_name("upper")] = bb[upper_col]

    # ---------- indicator inference ----------
    def _infer_needed_indicators_from_rules_and_derived(self) -> Set[str]:
        """
        rules/derived 텍스트에서 'ema.20', 'bb.20.lower' 같은 토큰을 수집합니다.
        (명시적 indicators에 없더라도 자동 계산하도록)
        """
        needed: Set[str] = set()

        def scan_text(txt: str) -> None:
            # ema.N
            for m in re.finditer(r"\bema\.(\d+)\b", txt, flags=re.IGNORECASE):
                needed.add(f"ema.{int(m.group(1))}")
            # bb.N.lower | middle | upper
            for m in re.finditer(r"\bbb\.(\d+)\.(lower|middle|upper)\b", txt, flags=re.IGNORECASE):
                needed.add(f"bb.{int(m.group(1))}.{m.group(2).lower()}")

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in {"lhs", "rhs", "key", "formula"} and isinstance(v, str):
                        scan_text(v)
                    walk(v)
            elif isinstance(obj, list):
                for it in obj:
                    walk(it)

        walk(self.strategy.get("rules", {}))
        walk(self.strategy.get("derived", []))
        return needed

    def _compute_missing_inferred_indicators(self, needed: Set[str]) -> None:
        """룰/파생식이 요구하는 지표 중 아직 없는 것만 계산."""
        missing = [tok for tok in needed if tok not in self.data.columns]
        if not missing:
            return

        # EMA
        ema_lengths = sorted({int(m.group(1)) for m in filter(None, (re.match(r"ema\.(\d+)$", t) for t in missing))})
        for L in ema_lengths:
            col = f"ema.{L}"
            if col not in self.data.columns:
                try:
                    self.data[col] = ta.ema(self.data["close"], length=L)
                except Exception as e:
                    logger.exception("Failed to compute inferred EMA(%d): %s", L, e)

        # BBANDS (요구되면 lower/middle/upper 전체 산출)
        bb_lengths = sorted({
            int(m.group(1))
            for m in filter(None, (re.match(r"bb\.(\d+)\.(lower|middle|upper)$", t) for t in missing))
        })
        for L in bb_lengths:
            std = self._find_bb_std_from_strategy_or_default(L)
            try:
                self._compute_bbands(L, std)  # key_prefix 없이 bb.L.suffix 로 생성
            except Exception as e:
                logger.exception("Failed to compute inferred BBANDS(%d, std=%s): %s", L, std, e)

    def _find_bb_std_from_strategy_or_default(self, length: int) -> float:
        for indicator in (self.strategy.get("indicators") or []):
            t = (indicator.get("type") or "").lower()
            if t in {"bollinger_bands", "bbands", "bb"}:
                params = indicator.get("params", {}) or {}
                L = int(params.get("length", -1))
                if L == length:
                    return float(params.get("stddev", params.get("std", 2)))
        return 2.0

    # ---------- derived formula eval (safe) ----------
    def _eval_derived_formula_safe(self, formula: str) -> pd.Series:
        """
        - shift(col, n) → self.data['col'].shift(n)
        - 점(.) 포함 컬럼명 안전치환(backtick 사용) 후 DataFrame.eval(engine='python')
        - raw python eval 지양 (가능한 한 DataFrame.eval 사용)
        """
        def _protect_cols(expr: str) -> str:
            cols = sorted(self.data.columns.tolist(), key=len, reverse=True)
            out = expr
            for col in cols:
                if f"`{col}`" in out:
                    continue
                out = re.sub(rf'(?<![`"\w]){re.escape(col)}(?![`"\w])', f"`{col}`", out)
            return out

        # shift 치환: shift(foo.bar, 2) → (`foo.bar`).shift(2)
        def _shift_repl(m: re.Match) -> str:
            col = m.group(1).strip()
            n = int(m.group(2))
            col_expr = f"`{col}`" if ('.' in col or ' ' in col) else col
            return f"({col_expr}).shift({n})"

        replaced = re.sub(r'shift\(\s*([A-Za-z0-9._\s]+)\s*,\s*(-?\d+)\s*\)', _shift_repl, formula)
        protected = _protect_cols(replaced)
        try:
            return self.data.eval(protected, engine="python")
        except Exception as e:
            logger.debug("DataFrame.eval failed for '%s' (%s), falling back to NaN series.", protected, e)
            return pd.Series(np.nan, index=self.data.index)

    # ---------- rule evaluation ----------
    def _evaluate_condition(self, condition: Dict[str, Any], i: int) -> bool:
        ct = (condition.get("type") or "").lower()

        def get_val(token: Any, idx: int) -> Optional[float]:
            if token is None:
                return None
            if isinstance(token, (int, float, np.floating)):
                return float(token)
            if isinstance(token, str):
                if token in self.data.columns:
                    v = self.data[token].iloc[idx]
                    try:
                        return float(v)
                    except Exception:
                        return None
                try:
                    return float(token)
                except Exception:
                    return None
            return None

        cmp_ops = {
            "<=": lambda x, y: x <= y,
            ">=": lambda x, y: x >= y,
            "<":  lambda x, y: x <  y,
            ">":  lambda x, y: x >  y,
            "==": lambda x, y: x == y,
        }

        if ct == "compare":
            op = condition.get("op")
            a = get_val(condition.get("lhs"), i)
            b = get_val(condition.get("rhs"), i) if condition.get("rhs") is not None else get_val(condition.get("value"), i)
            return (a is not None and b is not None and op in cmp_ops and cmp_ops[op](a, b))

        if ct == "threshold":
            op = condition.get("op")
            a = get_val(condition.get("lhs"), i)
            b = get_val(condition.get("value"), i)
            return (a is not None and b is not None and op in cmp_ops and cmp_ops[op](a, b))

        if ct == "crosses_above":
            lhs, rhs = condition.get("lhs"), condition.get("rhs")
            if i == 0 or lhs not in self.data.columns or rhs not in self.data.columns:
                return False
            return (self.data[lhs].iloc[i - 1] < self.data[rhs].iloc[i - 1]) and \
                   (self.data[lhs].iloc[i] > self.data[rhs].iloc[i])

        if ct == "crosses_below":
            lhs, rhs = condition.get("lhs"), condition.get("rhs")
            if i == 0 or lhs not in self.data.columns or rhs not in self.data.columns:
                return False
            return (self.data[lhs].iloc[i - 1] > self.data[rhs].iloc[i - 1]) and \
                   (self.data[lhs].iloc[i] < self.data[rhs].iloc[i])

        if ct == "touched_within":
            within = int(condition.get("within", 1))
            inner = condition.get("condition", {}) or {}
            start = max(0, i - within + 1)
            for j in range(start, i + 1):
                if self._evaluate_condition(inner, j):
                    return True
            return False

        logger.debug("Unknown condition type: %s", ct)
        return False

    # ---------- backtest core ----------
    def _execute_trades(self) -> None:
        """
        포지션: -1/0/1 (단순 롱/숏/현금). 수수료, 슬리피지는 미반영(동작 동일 유지).
        에퀴티 업데이트는 '직전 포지션 * 가격 변화' 누적 방식(기존 로직 유지).
        """
        n = len(self.data)
        self.data["signal"] = 0
        self.data["position"] = 0.0
        self.data["equity"] = float(self.initial_balance)

        trades: List[Trade] = []
        position: int = 0  # -1/0/1

        max_lookback = self._max_lookback_from_available_columns()
        start = max(1, max_lookback)
        self.data.loc[start - 1, "position"] = 0.0
        self.data.loc[start - 1, "equity"] = float(self.initial_balance)

        rules = self.strategy.get("rules", {}) or {}
        buy_rules = (rules.get("buy_condition") or {})
        sell_rules = (rules.get("sell_condition") or {})

        for i in range(start, n):
            # 1) Exit
            if position == 1:
                exits = buy_rules.get("exit", []) or []
                if any(self._evaluate_condition(cond, i) for cond in exits):
                    position = 0
                    trades.append(Trade(
                        timestamp=self.data["timestamp"].iloc[i],
                        price=float(self.data["close"].iloc[i]),
                        side="sell",
                    ))
            elif position == -1:
                exits = sell_rules.get("exit", []) or []
                if any(self._evaluate_condition(cond, i) for cond in exits):
                    position = 0
                    trades.append(Trade(
                        timestamp=self.data["timestamp"].iloc[i],
                        price=float(self.data["close"].iloc[i]),
                        side="buy",
                    ))

            # 2) Entry
            if position == 0:
                buy_entries = buy_rules.get("entry", []) or []
                sell_entries = sell_rules.get("entry", []) or []

                enter_long = bool(buy_entries) and all(self._evaluate_condition(cond, i) for cond in buy_entries)
                enter_short = bool(sell_entries) and all(self._evaluate_condition(cond, i) for cond in sell_entries)

                if enter_long:
                    position = 1
                    trades.append(Trade(
                        timestamp=self.data["timestamp"].iloc[i],
                        price=float(self.data["close"].iloc[i]),
                        side="buy",
                    ))
                elif enter_short:
                    position = -1
                    trades.append(Trade(
                        timestamp=self.data["timestamp"].iloc[i],
                        price=float(self.data["close"].iloc[i]),
                        side="sell",
                    ))

            # 3) 기록 & 에쿼티
            self.data.loc[i, "position"] = float(position)
            price_change = float(self.data["close"].iloc[i] - self.data["close"].iloc[i - 1])
            prev_equity = float(self.data["equity"].iloc[i - 1])
            prev_pos = float(self.data["position"].iloc[i - 1])
            self.data.loc[i, "equity"] = prev_equity + prev_pos * price_change

        # 결과 어댑트(기존 키 유지)
        self.results["trades"] = [
            {"timestamp": t.timestamp, "price": t.price, "side": t.side} for t in trades
        ]
        self.results["equity_curve"] = self.data[["timestamp", "equity"]].to_dict("records")

    def _max_lookback_from_available_columns(self) -> int:
        """
        ema.N, bb.N.* 가 존재하면 그 최대 N을 룩백으로 사용.
        또한 indicators에 명시된 length도 고려.
        """
        max_L = 0
        for col in self.data.columns:
            m = re.match(r"(ema|bb)\.(\d+)", col)
            if m:
                max_L = max(max_L, int(m.group(2)))
        for ind in (self.strategy.get("indicators") or []):
            L = int((ind.get("params", {}) or {}).get("length", 0))
            max_L = max(max_L, L)
        return max_L

    # ---------- metrics ----------
    def _calculate_metrics(self) -> None:
        eq = self.results.get("equity_curve", [])
        if not eq:
            self.results.update({"error": "No equity curve generated"})
            return
        equity_series = pd.Series(
            [row["equity"] for row in eq],
            index=pd.to_datetime([row["timestamp"] for row in eq]),
        )
        kpi_service = KpiService(equity_series, self.results.get("trades", []), self.initial_balance)
        try:
            kpis = kpi_service.calculate_kpis()
            self.results.update(kpis)
        except Exception as e:
            logger.exception("KPI calculation failed: %s", e)
