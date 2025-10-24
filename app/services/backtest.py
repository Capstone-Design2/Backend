# app/services/backtest.py
import re
from typing import Dict, List, Any, Optional, Set, Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta

from app.services.kpi_service import KpiService


class BacktestService:
    def __init__(self, strategy: Dict[str, Any], data: pd.DataFrame):
        self.strategy = strategy or {}
        self.data = data.copy()
        self.results: Dict[str, Any] = {}
        self.initial_balance: float = float(1_000_000)

    # ---------- public ----------
    def run(self) -> Dict[str, Any]:
        if not isinstance(self.data, pd.DataFrame) or len(self.data) < 2:
            return {"error": "Not enough data to run backtest"}

        # 정렬 및 기본 전처리
        if "timestamp" in self.data.columns:
            self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
            self.data = self.data.sort_values("timestamp").reset_index(drop=True)

        for c in ("open", "high", "low", "close", "volume"):
            if c in self.data.columns:
                self.data[c] = pd.to_numeric(self.data[c], errors="coerce")

        self._calculate_indicators()
        self._execute_trades()
        self._calculate_metrics()
        return self.results

    def _calculate_indicators(self):
        # 1) 기본 지표 계산
        for ind in self.strategy.get("indicators", []):
            t = ind["type"]
            k = ind["key"]
            p = ind.get("params", {})

            if t == "ema":
                self.data[k] = ta.ema(self.data["close"], length=p.get("length", 20))

            elif t == "bollinger_bands":
                bb = ta.bbands(
                    self.data["close"],
                    length=p.get("length", 20),
                    std=p.get("stddev", 2),   # json은 stddev, pandas-ta는 std
                )
                # ⬇️ 열 이름을 안전하게 매핑 (버전별 명칭 차이 대응)
                def first_col(prefix):
                    return next((c for c in bb.columns if str(c).startswith(prefix)), None)

                lower_col  = first_col("BBL_") or first_col("BBL")
                middle_col = first_col("BBM_") or first_col("BBM")
                upper_col  = first_col("BBU_") or first_col("BBU")

                if lower_col is None or middle_col is None or upper_col is None:
                    raise RuntimeError(f"Unexpected BBANDS columns: {list(bb.columns)}")

                self.data[f"{k}.lower"]  = bb[lower_col]
                self.data[f"{k}.middle"] = bb[middle_col]
                self.data[f"{k}.upper"]  = bb[upper_col]

        # 2) 파생 지표 계산 (점(.) 컬럼명 & shift() 지원)
        def _safe_eval(formula: str) -> str:
            # 컬럼명이 식별자 규칙을 어기면 backtick으로 감쌉니다.
            cols = sorted(self.data.columns.tolist(), key=len, reverse=True)
            safe = formula
            for col in cols:
                # 이미 backtick으로 감싸진 경우는 건너뜀
                if f"`{col}`" in safe:
                    continue
                # 정규식으로 정확히 해당 토큰만 치환
                safe = re.sub(rf'(?<![`"\w]){re.escape(col)}(?![`"\w])', f"`{col}`", safe)
            return safe

        for drv in self.strategy.get("derived", []):
            key = drv["key"]
            formula = drv.get("formula")
            if not formula:
                continue

            try:
                if "shift(" in formula:
                    # 아주 단순한 형태:  foo - shift(foo, 1)
                    m = re.match(r'^\s*([A-Za-z0-9._]+)\s*-\s*shift\(\s*([A-Za-z0-9._]+)\s*,\s*(\d+)\s*\)\s*$', formula)
                    if m:
                        a, b, n = m.group(1), m.group(2), int(m.group(3))
                        self.data[key] = self.data[a] - self.data[b].shift(n)
                    else:
                        # 그 외 일반식은 shift 부분만 치환 후 eval
                        def repl(match):
                            col = match.group(1)
                            n   = int(match.group(2))
                            return f"({f'`{col}`' if '.' in col or ' ' in col else col}).shift({n})"

                        tmp = re.sub(r'shift\(\s*([A-Za-z0-9._]+)\s*,\s*(\d+)\s*\)', repl, formula)
                        self.data[key] = self.data.eval(_safe_eval(tmp), engine="python")
                else:
                    self.data[key] = self.data.eval(_safe_eval(formula), engine="python")

                print(f"✅ Derived column '{key}' calculated.")

            except Exception as e:
                print(f"⚠️ Failed to compute derived column '{key}': {e}")

        print("--- Columns after indicator calculation ---")
        print(self.data.columns.tolist())

    def _compute_indicator_from_spec(self, indicator: Dict[str, Any]):
        ind_type = (indicator.get("type") or "").lower()
        params = indicator.get("params", {}) or {}
        key = indicator.get("key")

        if ind_type == "ema":
            length = int(params.get("length", 20))
            self.data[key] = ta.ema(self.data["close"], length=length)

        elif ind_type == "sma":
            length = int(params.get("length", 20))
            self.data[key] = ta.sma(self.data["close"], length=length)

        elif ind_type in ("bollinger_bands", "bbands", "bb"):
            length = int(params.get("length", 20))
            std = float(params.get("stddev", params.get("std", 2)))
            self._compute_bbands(length, std)

        # 필요시 추가 지표 확장 가능

    def _infer_needed_indicators_from_rules_and_derived(self) -> Set[str]:
        """rules/derived 안의 토큰에서 ema.N / bb.N.(lower|middle|upper) 요구사항을 추출"""
        needed: Set[str] = set()

        def scan_text(txt: str):
            # ema.20, ema.60 같은 토큰
            for m in re.finditer(r"\bema\.(\d+)\b", txt, flags=re.IGNORECASE):
                needed.add(f"ema.{int(m.group(1))}")
            # bb.20.lower/middle/upper
            for m in re.finditer(r"\bbb\.(\d+)\.(lower|middle|upper)\b", txt, flags=re.IGNORECASE):
                needed.add(f"bb.{int(m.group(1))}.{m.group(2).lower()}")

        # rules 전체 순회
        def walk(obj: Any):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("lhs", "rhs", "key", "formula"):
                        if isinstance(v, str):
                            scan_text(v)
                    walk(v)
            elif isinstance(obj, list):
                for it in obj:
                    walk(it)

        walk(self.strategy.get("rules", {}))
        walk(self.strategy.get("derived", []))

        return needed

    def _compute_missing_inferred_indicators(self, needed: Set[str]):
        # 이미 존재하는 컬럼은 제외
        missing = [tok for tok in needed if tok not in self.data.columns]
        if not missing:
            return

        # 필요한 ema 길이들
        ema_lengths = sorted({int(m.group(1)) for m in [re.match(r"ema\.(\d+)$", t) for t in missing] if m})
        for L in ema_lengths:
            col = f"ema.{L}"
            if col not in self.data.columns:
                self.data[col] = ta.ema(self.data["close"], length=L)

        # 필요한 bb 길이들(하나라도 필요하면 세 라인 모두 계산)
        bb_lengths = sorted({int(m.group(1)) for m in [re.match(r"bb\.(\d+)\.(lower|middle|upper)$", t) for t in missing] if m})
        for L in bb_lengths:
            # 표준편차는 전략에 명시된 값 우선, 없으면 2
            std = self._find_bb_std_from_strategy_or_default(L)
            self._compute_bbands(L, std)

    def _find_bb_std_from_strategy_or_default(self, length: int) -> float:
        # indicators에 명시된 stddev를 찾고, 없으면 2.0
        for indicator in (self.strategy.get("indicators") or []):
            t = (indicator.get("type") or "").lower()
            if t in ("bollinger_bands", "bbands", "bb"):
                params = indicator.get("params", {}) or {}
                L = int(params.get("length", -1))
                if L == length:
                    return float(params.get("stddev", params.get("std", 2)))
        return 2.0

    def _compute_bbands(self, length: int, std: float):
        bb = ta.bbands(self.data["close"], length=length, std=std)
        bbl = bb.filter(like="BBL").iloc[:, 0]
        bbm = bb.filter(like="BBM").iloc[:, 0]
        bbu = bb.filter(like="BBU").iloc[:, 0]
        self.data[f"bb.{length}.lower"] = bbl
        self.data[f"bb.{length}.middle"] = bbm
        self.data[f"bb.{length}.upper"] = bbu

    # ---------- formula eval ----------
    def _eval_formula(self, formula: str) -> pd.Series:
        """
        간단한 수식 평가:
        - shift(col, n) 지원 → self.data['col'].shift(n) 로 치환
        - self.data의 컬럼 토큰을 self.data['token']으로 치환
        """
        f = str(formula)

        def _shift_repl(m):
            col = m.group(1).strip()
            n = int(m.group(2))
            return f"self.data['{col}'].shift({n})"

        f = re.sub(r"shift\(\s*([A-Za-z0-9_.]+)\s*,\s*(-?\d+)\s*\)", _shift_repl, f)

        tokens = sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", f)), key=len, reverse=True)
        exclude = {"shift"}
        for t in tokens:
            if t in exclude:
                continue
            if t in self.data.columns:
                f = re.sub(rf"\b{re.escape(t)}\b", f"self.data['{t}']", f)

        try:
            out = eval(f)
        except Exception:
            out = pd.Series(np.nan, index=self.data.index)
        return out

    # ---------- conditions ----------
    def _evaluate_condition(self, condition: Dict[str, Any], i: int) -> bool:
        ct = (condition.get("type") or "").lower()

        def get_val(token, idx):
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
                        return v
                try:
                    return float(token)
                except Exception:
                    return None
            return None

        if ct == "compare":
            lhs = condition.get("lhs")
            rhs = condition.get("rhs")
            value = condition.get("value")
            op = condition.get("op")
            a = get_val(lhs, i)
            b = get_val(rhs, i) if rhs is not None else get_val(value, i)
            if a is None or b is None:
                return False
            ops = {"<=": lambda x,y: x <= y, ">=": lambda x,y: x >= y,
                   "<": lambda x,y: x < y, ">": lambda x,y: x > y, "==": lambda x,y: x == y}
            return ops.get(op, lambda *_: False)(a, b)

        if ct == "threshold":
            lhs = condition.get("lhs")
            op = condition.get("op")
            value = condition.get("value")
            a = get_val(lhs, i)
            b = get_val(value, i)
            if a is None or b is None:
                return False
            ops = {"<=": lambda x,y: x <= y, ">=": lambda x,y: x >= y,
                   "<": lambda x,y: x < y, ">": lambda x,y: x > y, "==": lambda x,y: x == y}
            return ops.get(op, lambda *_: False)(a, b)

        if ct == "crosses_above":
            lhs, rhs = condition.get("lhs"), condition.get("rhs")
            if i == 0 or lhs not in self.data.columns or rhs not in self.data.columns:
                return False
            return (self.data[lhs].iloc[i-1] < self.data[rhs].iloc[i-1]) and \
                   (self.data[lhs].iloc[i] > self.data[rhs].iloc[i])

        if ct == "crosses_below":
            lhs, rhs = condition.get("lhs"), condition.get("rhs")
            if i == 0 or lhs not in self.data.columns or rhs not in self.data.columns:
                return False
            return (self.data[lhs].iloc[i-1] > self.data[rhs].iloc[i-1]) and \
                   (self.data[lhs].iloc[i] < self.data[rhs].iloc[i])

        if ct == "touched_within":
            within = int(condition.get("within", 1))
            inner = condition.get("condition", {}) or {}
            start = max(0, i - within + 1)
            for j in range(start, i + 1):
                if self._evaluate_condition(inner, j):
                    return True
            return False

        return False

    # ---------- backtest core ----------
    def _execute_trades(self):
        self.data["signal"] = 0
        self.data["position"] = 0.0
        self.data["equity"] = float(self.initial_balance)

        trades: List[Dict[str, Any]] = []
        position: int = 0  # -1/0/1

        max_lookback = self._max_lookback_from_available_columns()
        start = max(1, max_lookback)
        self.data.loc[start-1, "position"] = 0.0
        self.data.loc[start-1, "equity"] = float(self.initial_balance)

        rules = self.strategy.get("rules", {}) or {}
        buy_rules = (rules.get("buy_condition") or {})
        sell_rules = (rules.get("sell_condition") or {})

        for i in range(start, len(self.data)):
            # 1) Exit
            if position == 1:
                exits = buy_rules.get("exit", []) or []
                if any(self._evaluate_condition(cond, i) for cond in exits):
                    position = 0
                    trades.append({"timestamp": self.data["timestamp"].iloc[i],
                                   "price": float(self.data["close"].iloc[i]),
                                   "side": "sell"})
            elif position == -1:
                exits = sell_rules.get("exit", []) or []
                if any(self._evaluate_condition(cond, i) for cond in exits):
                    position = 0
                    trades.append({"timestamp": self.data["timestamp"].iloc[i],
                                   "price": float(self.data["close"].iloc[i]),
                                   "side": "buy"})

            # 2) Entry
            if position == 0:
                buy_entries = buy_rules.get("entry", []) or []
                sell_entries = sell_rules.get("entry", []) or []
                enter_long = bool(buy_entries) and all(self._evaluate_condition(cond, i) for cond in buy_entries)
                enter_short = bool(sell_entries) and all(self._evaluate_condition(cond, i) for cond in sell_entries)

                if enter_long:
                    position = 1
                    trades.append({"timestamp": self.data["timestamp"].iloc[i],
                                   "price": float(self.data["close"].iloc[i]),
                                   "side": "buy"})
                elif enter_short:
                    position = -1
                    trades.append({"timestamp": self.data["timestamp"].iloc[i],
                                   "price": float(self.data["close"].iloc[i]),
                                   "side": "sell"})

            # 3) 기록 & 에쿼티
            self.data.loc[i, "position"] = float(position)
            price_change = float(self.data["close"].iloc[i] - self.data["close"].iloc[i-1])
            prev_equity = float(self.data["equity"].iloc[i-1])
            prev_pos = float(self.data["position"].iloc[i-1])
            self.data.loc[i, "equity"] = prev_equity + prev_pos * price_change

        self.results["trades"] = trades
        self.results["equity_curve"] = self.data[["timestamp", "equity"]].to_dict("records")

    def _max_lookback_from_available_columns(self) -> int:
        """ema.N, bb.N.* 가 존재하면 그 최대 N을 룩백으로 사용"""
        max_L = 0
        for col in self.data.columns:
            m = re.match(r"(ema|bb)\.(\d+)", col)
            if m:
                max_L = max(max_L, int(m.group(2)))
        # 명시된 indicators 기준도 고려
        for ind in (self.strategy.get("indicators") or []):
            L = int((ind.get("params", {}) or {}).get("length", 0))
            max_L = max(max_L, L)
        return max_L

    # ---------- metrics ----------
    def _calculate_metrics(self):
        eq = self.results.get("equity_curve", [])
        equity_series = pd.Series([row["equity"] for row in eq],
                                  index=pd.to_datetime([row["timestamp"] for row in eq]))
        kpi_service = KpiService(equity_series, self.results.get("trades", []), self.initial_balance)
        kpis = kpi_service.calculate_kpis()
        self.results.update(kpis)
