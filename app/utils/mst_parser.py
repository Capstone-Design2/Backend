from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple
import re
import zipfile

# ==============================
# 기본 유틸
# ==============================

ISIN_RE = re.compile(r"KR[A-Z0-9]{10}")
SIX_DIGIT = re.compile(r"^\d{6}$")

def _decode_bytes(data: bytes) -> Tuple[str, str]:
    for enc in ("cp949", "euc-kr", "utf-8", "latin1"):
        try:
            return data.decode(enc), enc
        except Exception:
            continue
    return data.decode("latin1", errors="replace"), "latin1(replace)"

def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\x00", " ")).strip()

# ==============================
# 파일 읽기
# ==============================

def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            name = next((n for n in zf.namelist() if n.lower().endswith((".mst", ".txt", ".dat"))), zf.namelist()[0])
            raw = zf.read(name)
    else:
        raw = path.read_bytes()
    text, _ = _decode_bytes(raw)
    return text

# ==============================
# 파일명으로 시장 자동 추론
# ==============================

def _guess_market(filename: str) -> Optional[str]:
    name = filename.lower()
    if "kospi" in name:
        return "KOSPI"
    if "kosdaq" in name:
        return "KOSDAQ"
    if "konex" in name:
        return "KONEX"
    return None

# ==============================
# 라인 파싱 (주식 전용)
# ==============================

def _parse_line(line: str) -> Optional[Tuple[str, str, str]]:
    """라인에서 (pdno, isin, name) 추출"""
    m = ISIN_RE.search(line)
    if not m:
        return None
    isin = m.group(0)
    left = line[:m.start()].strip()
    right = line[m.end():]
    if not left:
        return None
    pdno = left.split()[-1]
    name = re.split(r"\s{2,}(?=[A-Z0-9])", right, maxsplit=1)[0]
    return pdno, isin, _clean_spaces(name)

# ==============================
# 메인 파서 (주식만)
# ==============================

def parse_mst_zip(zip_path: Path, default_market: Optional[str] = None) -> List[dict]:
    """
    zip(.mst) 파일을 파싱하여 [{"pdno":..., "isin":..., "name":..., "market":...}] 반환
    - 시장 자동 추론
    - 주식(6자리 코드)만 필터링
    """
    assert zip_path.exists(), f"not found: {zip_path}"

    text = _read_text(zip_path)
    market = default_market or _guess_market(zip_path.name) or "KOSPI"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    rows: List[dict] = []
    for ln in lines:
        parsed = _parse_line(ln)
        if not parsed:
            continue
        pdno, isin, name = parsed
        
        if not SIX_DIGIT.fullmatch(pdno):
            continue
        rows.append({"pdno": pdno, "isin": isin, "name": name, "market": market})

    # (pdno, market) 기준 중복 제거
    dedup = {}
    for r in rows:
        dedup[(r["pdno"], r["market"])] = r

    return list(dedup.values())
