"""Diagnose the database referenced by DATABASE_URL.

Prints which DB we're on, row counts, the profile table schema, and simulates
the register flush (insert user + profile) to see if it succeeds locally.

Usage (PowerShell):
    $env:DATABASE_URL = "postgresql+psycopg://..."
    python -m scripts.diag_db
"""
from __future__ import annotations

import uuid

from sqlalchemy import inspect

from app.db.models import Profile, User
from app.db.session import SessionLocal, engine
from app.services.auth import hash_password


def main() -> int:
    print("URL:", engine.url.render_as_string(hide_password=True))
    db = SessionLocal()
    try:
        print("users count:", db.query(User).count())
        print("profiles count:", db.query(Profile).count())

        insp = inspect(engine)
        cols = [c["name"] for c in insp.get_columns("profile")]
        print("profile columns:", cols)
        print("profile PK:", insp.get_pk_constraint("profile").get("constrained_columns"))

        # Simulate the register flush against THIS database
        uid = uuid.uuid4()
        uname = "localdiag_" + str(uid)[:8]
        db.add(User(id=uid, username=uname, password_hash=hash_password("diagpass123")))
        db.add(Profile(user_id=uid, cuisine_prefs=[], spicy=2, dislikes=[]))
        try:
            db.flush()
            print("SIMULATED REGISTER FLUSH: OK (schema is correct, insert works)")
        except Exception as e:  # noqa: BLE001
            print("SIMULATED REGISTER FLUSH FAILED:", type(e).__name__, str(e)[:300])
        finally:
            db.rollback()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
