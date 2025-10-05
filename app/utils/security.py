import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = os.getenv("JWT_SECRET", "change-me-please")  # .env로 분리 권장
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    # bcrypt는 72바이트 이상을 지원하지 않으므로 자름
    if len(password.encode("utf-8")) > 72:
        password = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

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

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
