"""
DateTime Utility Module
UTC 타임존 처리를 위한 유틸리티 함수들

모든 datetime은 UTC 타임존을 포함해야 합니다.
이 모듈의 함수들을 사용하여 일관된 시간 처리를 보장합니다.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """
    UTC 타임존이 포함된 현재 시간을 반환

    Returns:
        datetime: UTC 타임존이 포함된 현재 시간

    Example:
        >>> now = utc_now()
        >>> now.tzinfo == timezone.utc
        True
    """
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    datetime을 UTC 타임존으로 변환
    naive datetime인 경우 UTC로 간주하여 타임존 추가

    Args:
        dt: 변환할 datetime 객체

    Returns:
        datetime: UTC 타임존이 포함된 datetime

    Example:
        >>> naive_dt = datetime(2025, 1, 1, 12, 0, 0)
        >>> utc_dt = ensure_utc(naive_dt)
        >>> utc_dt.tzinfo == timezone.utc
        True
    """
    if dt.tzinfo is None:
        # naive datetime은 UTC로 간주
        logger.debug(f"Converting naive datetime to UTC: {dt}")
        return dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        # 다른 타임존은 UTC로 변환
        logger.debug(f"Converting {dt.tzinfo} to UTC: {dt}")
        return dt.astimezone(timezone.utc)
    return dt


def to_utc_string(dt: Optional[datetime]) -> Optional[str]:
    """
    datetime을 UTC ISO 8601 문자열로 변환

    Args:
        dt: 변환할 datetime 객체 (None 가능)

    Returns:
        str: UTC ISO 8601 형식 문자열 (None인 경우 None 반환)

    Example:
        >>> dt = utc_now()
        >>> iso_str = to_utc_string(dt)
        >>> iso_str.endswith('+00:00')
        True
    """
    if dt is None:
        return None
    return ensure_utc(dt).isoformat()


def from_utc_string(dt_str: Optional[str]) -> Optional[datetime]:
    """
    UTC ISO 8601 문자열을 datetime으로 변환

    Args:
        dt_str: ISO 8601 형식 문자열 (None 가능)

    Returns:
        datetime: UTC 타임존이 포함된 datetime (None인 경우 None 반환)

    Example:
        >>> dt_str = "2025-01-01T12:00:00+00:00"
        >>> dt = from_utc_string(dt_str)
        >>> dt.tzinfo == timezone.utc
        True
    """
    if dt_str is None:
        return None

    dt = datetime.fromisoformat(dt_str)
    return ensure_utc(dt)


def add_days(dt: datetime, days: int) -> datetime:
    """
    datetime에 일수를 더함 (UTC 유지)

    Args:
        dt: 기준 datetime
        days: 더할 일수 (음수 가능)

    Returns:
        datetime: 일수가 더해진 datetime (UTC)
    """
    return ensure_utc(dt) + timedelta(days=days)


def add_hours(dt: datetime, hours: int) -> datetime:
    """
    datetime에 시간을 더함 (UTC 유지)

    Args:
        dt: 기준 datetime
        hours: 더할 시간 (음수 가능)

    Returns:
        datetime: 시간이 더해진 datetime (UTC)
    """
    return ensure_utc(dt) + timedelta(hours=hours)


# Export all public functions
__all__ = [
    'utc_now',
    'ensure_utc',
    'to_utc_string',
    'from_utc_string',
    'add_days',
    'add_hours',
]
