import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from jose import jwt, JWTError
import bcrypt

SECRET_KEY = os.getenv("JWT_SECRET", "change-me-please")  # .env로 분리 권장
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _truncate_password(password: str) -> bytes:
    """
    bcrypt는 72바이트까지만 처리하므로, 초과하면 UTF-8 문자 경계를 고려하여 자름
    Returns bytes for bcrypt
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password_bytes

    # UTF-8 문자가 중간에 잘리지 않도록 문자 단위로 처리
    truncated = password
    while len(truncated.encode("utf-8")) > 72:
        truncated = truncated[:-1]
    return truncated.encode("utf-8")

def get_password_hash(password: str) -> str:
    """
    비밀번호를 bcrypt로 해시화합니다.
    """
    password_bytes = _truncate_password(password)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    """
    비밀번호를 검증합니다.
    """
    plain_bytes = _truncate_password(plain)
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hashed_bytes)

def _create_token(subject: dict, expires_delta: timedelta) -> str:
    to_encode = subject.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(sub: str, role: str):
    return _create_token({"sub": sub, "scope": "access", "role": role},
                         timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

def create_refresh_token(sub: str):
    return _create_token({"sub": sub, "scope": "refresh"},
                         timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
