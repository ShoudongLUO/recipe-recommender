from __future__ import annotations

import bcrypt

from app.config import settings

# Password length is enforced ≤ 72 bytes by Pydantic in routes/auth.py;
# this module assumes that and uses bcrypt directly (standard bcrypt hash format).
# We avoid passlib because passlib 1.7.4 is broken on bcrypt >= 5.0 (issue 190).


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


import uuid as _uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError, ExpiredSignatureError


DEFAULT_TOKEN_TTL_SECONDS = 30 * 24 * 3600  # 30 days
ALGORITHM = "HS256"


class AuthError(Exception):
    pass


def create_token(
    *,
    user_id: _uuid.UUID,
    username: str,
    expires_in: int = DEFAULT_TOKEN_TTL_SECONDS,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except ExpiredSignatureError as e:
        raise AuthError("Token expired") from e
    except JWTError as e:
        raise AuthError("Invalid token") from e


from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db


def current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[len("Bearer "):]
    try:
        payload = decode_token(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    try:
        user_id = _uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
