"""Create all tables in the database referenced by DATABASE_URL.

Usage (PowerShell, against Neon Postgres):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.migrate

Usage (local SQLite, for sanity-checking):
    python -m scripts.migrate
"""
from __future__ import annotations

from app.db.models import Base
from app.db.session import engine


def main() -> int:
    print(f"Creating tables on: {engine.url.render_as_string(hide_password=True)}")
    Base.metadata.create_all(bind=engine)
    print("Done. Tables present:")
    for name in sorted(Base.metadata.tables.keys()):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
