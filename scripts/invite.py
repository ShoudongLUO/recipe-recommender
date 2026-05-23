"""Generate invite codes and (optionally) insert them into the DB.

Usage:
    python -m scripts.invite              # generate 1 code, insert, print
    python -m scripts.invite 5            # generate 5
    python -m scripts.invite --dry-run    # just print, don't write to DB
"""
from __future__ import annotations

import secrets
import string
import sys

FORBIDDEN_CHARS = set("0O1Il")
ALPHABET = "".join(c for c in (string.ascii_letters + string.digits) if c not in FORBIDDEN_CHARS)
CODE_LENGTH = 12


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    n = int(args[0]) if len(args) >= 1 else 1

    codes = [generate_code() for _ in range(n)]
    if dry:
        for c in codes:
            print(c)
        return 0

    from app.db.models import InviteCode
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        for c in codes:
            db.add(InviteCode(code=c))
            print(c)
        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
