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
