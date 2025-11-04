# app/services/backtest.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta

from app.utils.kpi_calc import KpiCalc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trade:
    """
    단일 체결(매수/매도) 정보를 표현하는 불변 데이터 클래스.

    Attributes
    ----------
    timestamp : pd.Timestamp
        체결 시각(캔들 시각과 동일한 시간 축 사용)
    price : float
        체결 가격(종가 기준으로 진입/청산)
    side : str
        'buy' 또는 'sell'
    """
    timestamp: pd.Timestamp
    price: float
    side: str  # "buy" | "sell"


class BacktestService:
    """
    단일 전략(dict)을 입력받아 시세 데이터프레임에 대해
    - 지표(indicators) 계산
    - 파생(derived) 컬럼 계산
    - 룰 평가(진입/청산 시그널 산출)
    - 포지션/에쿼티 곡선 계산
    - KPI(CAGR, Sharpe, MDD 등) 산출
    까지 한 번에 수행하는 서비스 클래스.

    Parameters
    ----------
    strategy : Dict[str, Any]
        strategy.json 혹은 DB에서 가져온 단일 전략 정의
        (indicators/derived/rules 필드 포함을 기대)
    data : pd.DataFrame
        'timestamp','open','high','low','close','volume' 컬럼을 포함한 시세 데이터

    Attributes
    ----------
    results : Dict[str, Any]
        실행 결과(거래내역, 에쿼티 커브, KPI 등)
    initial_balance : float
        초기자산(에쿼티 시작값). 기본 1,000,000
    """
    def __init__(self, strategy: Dict[str, Any], data: pd.DataFrame):
        self.strategy = strategy or {}
        self.data = data.copy()
        self.results: Dict[str, Any] = {}
        self.initial_balance: float = float(1_000_000)

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        """
        백테스트 전체 파이프라인을 실행한다.

        순서:
        1) 데이터 전처리 (_prep_dataframe)
        2) 룰/파생식에서 필요한 지표 자동 추론 및 누락분 계산
        (_infer_needed_indicators_from_rules_and_derived → _compute_missing_inferred_indicators)
        3) 명시된 indicators/derived 계산 (_calculate_indicators)
        4) 거래 시뮬레이션 및 에쿼티 곡선 생성 (_execute_trades)
        5) KPI 계산 (_calculate_metrics)

        Returns
        -------
        Dict[str, Any]
            - "trades": [{timestamp, price, side}, ...]
            - "equity_curve": [{timestamp, equity}, ...]
            - KPI들(CAGR, Sharpe, MDD 등; KpiService 구현에 따름)
            데이터가 부족한 경우 {"error": "..."} 형태.
        """
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
        """
        입력 데이터 공통 전처리.

        - 'timestamp'를 datetime으로 변환, NaT 제거
        - timestamp 기준 정렬 및 RangeIndex 재설정
        - 가격/거래량 컬럼을 수치형으로 강제 변환
        - 과거 실행 잔여 컬럼('signal','position','equity')이 있으면 제거

        Raises
        ------
        ValueError
            'timestamp' 컬럼이 존재하지 않을 때
        """
        if "timestamp" in self.data.columns:
            self.data["timestamp"] = pd.to_datetime(self.data["timestamp"], errors="coerce")
            self.data = self.data.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        else:
            raise ValueError("Input data must contain 'timestamp' column")

        for c in ("open", "high", "low", "close", "volume"):
            if c in self.data.columns:
                self.data[c] = pd.to_numeric(self.data[c], errors="coerce")

        # 이전 실행 흔적 제거
        for col in ("signal", "position", "equity"):
            if col in self.data.columns:
                self.data.drop(columns=[col], inplace=True)

    # ---------- indicators & derived ----------
    def _calculate_indicators(self) -> None:
        """
        strategy['indicators'] / strategy['derived'] 정의에 따라 컬럼을 계산하여 self.data에 추가한다.

        지원 지표
        --------
        - EMA: type='ema', key='ema.20' (length 파라미터 사용)
        - SMA: type='sma', key='sma.20'
        - 볼린저 밴드: type in {'bollinger_bands','bbands','bb'}
        key는 접두(prefix)로 사용되며, '{key}.lower/middle/upper'가 생성됨.
        key를 생략하고 추론 계산 시에는 'bb.{length}.lower/middle/upper'가 생성됨.

        파생 지표
        --------
        - derived[*].formula 를 안전하게 평가(_eval_derived_formula_safe)하여 Series 생성
        - shift(col, n) 지원
        - 점(.) 포함 컬럼은 백틱(`)으로 보호하여 DataFrame.eval(engine="python") 사용
        """
        # 1) 기본 지표 계산
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

        # 2) 파생 지표 계산
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
        볼린저 밴드 계산 헬퍼.

        pandas-ta 버전별로 컬럼명이 미묘하게 다른 문제를 보완하여
        lower/middle/upper를 안정적으로 찾아 출력한다.

        Parameters
        ----------
        length : int
            이동평균 길이
        std : float
            표준편차 배수
        key_prefix : Optional[str]
            출력 컬럼 접두. 예: 'bb.20' 지정 시 'bb.20.lower/middle/upper' 생성.
            None이면 'bb.{length}.lower/middle/upper' 형식 사용.
        """
        bb = ta.bbands(self.data["close"], length=length, std=std)

        # 내부 유틸: 접두가 다른 경우도 포괄적으로 매칭
        def _first_col(prefix: str) -> Optional[str]:
            return next((c for c in bb.columns if str(c).startswith(prefix)), None)

        lower_col = _first_col("BBL_") or _first_col("BBL")
        middle_col = _first_col("BBM_") or _first_col("BBM")
        upper_col = _first_col("BBU_") or _first_col("BBU")

        if not (lower_col and middle_col and upper_col):
            raise RuntimeError(f"Unexpected BBANDS columns: {list(bb.columns)}")

        # 출력 컬럼명 빌더
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
        strategy['rules'] / strategy['derived'] 텍스트 내 토큰을 스캔하여
        명시되지 않았더라도 필요한 지표를 자동 추론한다.

        스캔 대상 예시
        -------------
        - 'ema.20'
        - 'bb.20.lower' / 'bb.20.middle' / 'bb.20.upper'

        Returns
        -------
        Set[str]
            추론된 지표 토큰들의 집합
        """
        needed: Set[str] = set()

        def scan_text(txt: str) -> None:
            # ema.N
            for m in re.finditer(r"\bema\.(\d+)\b", txt, flags=re.IGNORECASE):
                needed.add(f"ema.{int(m.group(1))}")
            # bb.N.lower|middle|upper
            for m in re.finditer(r"\bbb\.(\d+)\.(lower|middle|upper)\b", txt, flags=re.IGNORECASE):
                needed.add(f"bb.{int(m.group(1))}.{m.group(2).lower()}")

        def walk(obj: Any) -> None:
            # dict/list를 재귀 순회하며 텍스트 필드를 스캔
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
        """
        추론된 지표 중 현재 데이터프레임에 없는 컬럼만 계산한다.

        - EMA: 필요한 길이별로 ta.ema 계산
        - BBANDS: lower/middle/upper 중 하나라도 요구되면 세 컬럼 모두 산출
            (std는 전략 정의에서 동일 length의 std를 우선 사용, 없으면 2.0)
        """
        missing = [tok for tok in needed if tok not in self.data.columns]
        if not missing:
            return

        # EMA 일괄 계산
        ema_lengths = sorted({int(m.group(1)) for m in filter(None, (re.match(r"ema\.(\d+)$", t) for t in missing))})
        for L in ema_lengths:
            col = f"ema.{L}"
            if col not in self.data.columns:
                try:
                    self.data[col] = ta.ema(self.data["close"], length=L)
                except Exception as e:
                    logger.exception("Failed to compute inferred EMA(%d): %s", L, e)

        # BBANDS 일괄 계산 (요구되면 세 라인 모두 생성)
        bb_lengths = sorted({
            int(m.group(1))
            for m in filter(None, (re.match(r"bb\.(\d+)\.(lower|middle|upper)$", t) for t in missing))
        })
        for L in bb_lengths:
            std = self._find_bb_std_from_strategy_or_default(L)
            try:
                # key_prefix 없이 생성 → 'bb.L.suffix'
                self._compute_bbands(L, std)
            except Exception as e:
                logger.exception("Failed to compute inferred BBANDS(%d, std=%s): %s", L, std, e)

    def _find_bb_std_from_strategy_or_default(self, length: int) -> float:
        """
        전략 정의에서 length가 일치하는 볼린저 표준편차(stddev/std)를 우선 찾고,
        없으면 기본값 2.0을 반환한다.
        """
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
        파생식(formula)을 비교적 안전하게 평가하여 Series를 반환한다.

        지원 문법
        --------
        - shift(col, n)  → self.data['col'].shift(n)
        - 점(.)/공백이 포함된 컬럼명은 자동으로 백틱(`)으로 보호
        - pandas.DataFrame.eval(engine='python') 사용
        (실패 시 동일 길이 NaN Series 반환)

        Parameters
        ----------
        formula : str
            예: "close / ema.20 - 1", "shift(ema.20, 1)"

        Returns
        -------
        pd.Series
            평가 결과 Series (index는 self.data.index와 동일)
        """
        def _protect_cols(expr: str) -> str:
            cols = sorted(self.data.columns.tolist(), key=len, reverse=True)
            out = expr
            for col in cols:
                if f"`{col}`" in out:
                    continue
                # 토큰 경계에서만 치환(다른 식별자 일부로 오인치환 방지)
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
        """
        단일 조건 객체(condition)를 i번째 행 기준으로 평가하여 True/False를 반환한다.

        지원 조건 타입
        --------------
        - "compare"   : lhs (op) rhs|value   예) ema.20 > close
        - "threshold" : lhs (op) value       예) close >= 100000
        - "crosses_above": lhs가 rhs를 상향 돌파 (직전<, 현재>)
        - "crosses_below": lhs가 rhs를 하향 돌파 (직전>, 현재<)
        - "touched_within": 최근 N개 봉 중 inner condition이 1번이라도 True

        파라미터 해석
        -------------
        - lhs/rhs/value는 숫자 또는 self.data의 컬럼명 문자열을 허용
        - 비교 연산자: <, <=, >, >=, ==

        Parameters
        ----------
        condition : Dict[str, Any]
            조건 정의 딕셔너리
        i : int
            평가할 데이터프레임의 인덱스(행 번호)

        Returns
        -------
        bool
            조건이 충족되면 True, 아니면 False
        """
        ct = (condition.get("type") or "").lower()

        def get_val(token: Any, idx: int) -> Optional[float]:
            # 숫자/문자열(컬럼명 또는 숫자 문자열) → float
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
        룰에 따라 포지션을 업데이트하고 에쿼티 곡선을 생성한다.

        포지션 정의
        -----------
        -1: 숏, 0: 현금, 1: 롱  (현재 구현은 롱/숏 동시 보유 미지원)

        에쿼티 업데이트
        ---------------
        - '직전 포지션 * (현재종가 - 이전종가)' 방식으로 누적
        - 수수료/슬리피지는 미반영(기존 로직 유지)

        시그널 처리
        -----------
        - 진입(entry): buy_condition.entry / sell_condition.entry 의 모든 조건이 True일 때만 진입
        - 청산(exit):  보유 포지션에 대응하는 exit 조건 중 하나라도 True면 청산
        """
        n = len(self.data)
        self.data["signal"] = 0
        self.data["position"] = 0.0
        self.data["equity"] = float(self.initial_balance)

        trades: List[Trade] = []
        position: int = 0  # -1/0/1

        # 지표 룩백으로 첫 계산 가능 시점 보정
        max_lookback = self._max_lookback_from_available_columns()
        start = max(1, max_lookback)
        self.data.loc[start - 1, "position"] = 0.0
        self.data.loc[start - 1, "equity"] = float(self.initial_balance)

        rules = self.strategy.get("rules", {}) or {}
        buy_rules = (rules.get("buy_condition") or {})
        sell_rules = (rules.get("sell_condition") or {})

        for i in range(start, n):
            # 1) Exit (보유 포지션에 따라 다른 exit 세트 평가)
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

            # 2) Entry (현금 상태에서만 진입)
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
        데이터프레임에 존재하는 지표 컬럼명(ema.N, bb.N.*)과
        strategy['indicators']의 length를 확인해
        룩백이 필요한 최대 길이를 반환한다.

        Returns
        -------
        int
            룩백에 필요한 최대 N (최소 0)
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
        """
        self.results['equity_curve']를 사용하여 KPI를 계산한다.

        동작
        ----
        - equity_curve를 시계열(pd.Series)로 변환
        - KpiService(equity_series, trades, initial_balance).calculate_kpis() 호출
        - 계산된 KPI를 self.results에 병합

        실패 처리
        ---------
        - equity_curve가 없으면 self.results에 {"error": "..."} 저장
        - KPI 계산 중 예외 발생 시 로그만 남기고 진행(결과에 KPI 미포함)
        """
        eq = self.results.get("equity_curve", [])
        if not eq:
            self.results.update({"error": "No equity curve generated"})
            return
        equity_series = pd.Series(
            [row["equity"] for row in eq],
            index=pd.to_datetime([row["timestamp"] for row in eq]),
        )
        kpi_service = KpiCalc(equity_series, self.results.get("trades", []), self.initial_balance)
        try:
            kpis = kpi_service.calculate_kpis()
            self.results.update(kpis)
        except Exception as e:
            logger.exception("KPI calculation failed: %s", e)
