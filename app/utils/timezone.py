from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

def kst_ymd_to_utc_naive(yyyymmdd: str) -> datetime:
    dt_kst = datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=KST)
    return dt_kst.astimezone(timezone.utc).replace(tzinfo=None)

def kst_ymd_hms_to_utc_naive(yyyymmdd: str, hhmmss: str) -> datetime:
    dt_kst = datetime.strptime(yyyymmdd + hhmmss, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    return dt_kst.astimezone(timezone.utc).replace(tzinfo=None)