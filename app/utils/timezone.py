from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import re
from fastapi import HTTPException

KST = ZoneInfo("Asia/Seoul")
DATE_RE = re.compile(r"^\d{8}$")

def kst_ymd_to_utc_naive(yyyymmdd: str) -> datetime:
    dt_kst = datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=KST)
    return dt_kst.astimezone(timezone.utc).replace(tzinfo=None)

def kst_ymd_hms_to_utc_naive(yyyymmdd: str, hhmmss: str) -> datetime:
    dt_kst = datetime.strptime(yyyymmdd + hhmmss, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    return dt_kst.astimezone(timezone.utc).replace(tzinfo=None)

def ymd_years_ago_kst(ymd: str, years: int) -> str:
    dt = datetime.strptime(ymd, "%Y%m%d").replace(tzinfo=KST)
    try:
        target = dt.replace(year=dt.year - years)
    except ValueError:
        target = dt.replace(month=2, day=28, year=dt.year - years)
    return target.strftime("%Y%m%d")

def today_kst_datetime() -> datetime:
    return datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)

def months_ago_kst(d: datetime, months: int) -> datetime:
    y, m = d.year, d.month
    m -= months
    y -= (m <= 0)
    m = m + 12 if m <= 0 else m
    
    day = min(d.day, [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,31,30,31,30,31,31,30,31,30,31][m-1])
    return datetime(y, m, day, tzinfo=KST)

def daterange_kst(start: datetime, end: datetime):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)
        
def fmt_ymd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")

def assert_yyyymmdd(name: str, value: str) -> None:
    if not DATE_RE.match(value or ""):
        raise HTTPException(
            status_code=400, detail=f"{name}는 YYYYMMDD 형식이어야 합니다.")