# utils/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session as get_db
from app.repositories.user_repository import UserRepository
from app.utils.security import decode_token

auth_scheme = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials  # <-- "Bearer xxx"에서 xxx 추출
    payload = decode_token(token)
    if not payload or payload.get("scope") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    email = payload.get("sub")
    repo = UserRepository()
    user = await repo.get_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
