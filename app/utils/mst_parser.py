# app/utils/mst_parser.py
from __future__ import annotations
from pathlib import Path
import re
import zipfile
from typing import List, Tuple

# 메인 패턴: 6자리 코드 + 공백 + ISIN + 종목명 + (두 칸 이상 공백) + 'ST...'
LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<pdno>\d{6})          # 6 digits code
    \s+                      # spaces
    (?P<isin>KR[0-9A-Z]{10}) # ISIN (KR + 10)
    (?P<name>.+?)            # greedy-but-lazy name
    \s{2,}ST                 # two+ spaces then 'ST' token
    """,
    re.VERBOSE,
)

# 폴백 패턴: ST 못 찾는 라인이나 변형 라인 대비
FALLBACK_RE = re.compile(
    r"""
    ^\s*
    (?P<pdno>\d{6})\s+
    (?P<isin>KR[0-9A-Z]{10})
    (?P<name>.*)             # 라인 끝까지 이름 후보
    """,
    re.VERBOSE,
)

def _decode_bytes(data: bytes) -> Tuple[str, str]:
    # KRX/KIS 파일은 대부분 CP949
    for enc in ("cp949", "euc-kr", "utf-8", "latin1"):
        try:
            return data.decode(enc), enc
        except Exception:
            continue
    return data.decode("latin1", errors="replace"), "latin1(replace)"

def _clean_name(raw: str) -> str:
    # 좌우 공백 정리 + 내부 다중 공백 정규화
    s = raw.strip().replace("\x00", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _parse_line(line: str) -> dict | None:
    m = LINE_RE.search(line)
    if m:
        d = m.groupdict()
        d["name"] = _clean_name(d["name"])
        return d

    # 폴백: ST 토큰이 없거나 변형인 경우, 이름을 공백 블록 기준으로 잘라봄
    m2 = FALLBACK_RE.search(line)
    if m2:
        d = m2.groupdict()
        # 이름 후보에서 뒤쪽 숫자/토큰 덩어리 제거 휴리스틱
        # - 두 칸 이상 공백 뒤에 연속 숫자/대문자 덩어리가 나오면 거기서 컷
        name = d["name"]
        name = re.split(r"\s{2,}(?=[A-Z0-9])", name, maxsplit=1)[0]
        d["name"] = _clean_name(name)
        return d

    return None

def parse_mst_zip(zip_path: Path, default_market: str) -> List[dict]:
    """
    zip 안의 .mst 계열 파일을 파싱하여 아래 스키마로 반환:
      [{"pdno":"000250", "isin":"KR7000250001", "name":"삼천당제약", "market":"NXT_KOSDAQ"}, ...]
    """
    assert zip_path.exists(), f"not found: {zip_path}"

    # 대상 파일 선택
    with zipfile.ZipFile(zip_path, "r") as zf:
        target = None
        for name in zf.namelist():
            low = name.lower()
            if low.endswith((".mst", ".mst.txt", ".dat", ".txt")):
                target = name
                break
        if target is None:
            # 첫 파일로라도 시도
            target = zf.namelist()[0]
        raw = zf.read(target)

    text, enc = _decode_bytes(raw)
    lines = [ln.rstrip("\r\n") for ln in text.splitlines() if ln.strip()]

    rows: list[dict] = []
    for ln in lines:
        parsed = _parse_line(ln)
        if not parsed:
            continue

        # 필수 값 보정
        pdno = parsed["pdno"]
        isin = parsed.get("isin")
        name = parsed.get("name")

        if not (pdno and isin and name):
            continue

        rows.append({
            "pdno": pdno,
            "isin": isin,
            "name": name,
            "market": default_market,
        })

    # (pdno, market) 기준 중복 제거
    dedup = {}
    for r in rows:
        dedup[(r["pdno"], r["market"])] = r
    return list(dedup.values())
