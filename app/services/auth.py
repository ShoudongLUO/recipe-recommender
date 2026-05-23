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
