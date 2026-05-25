"""Drop and recreate all tables on the database referenced by DATABASE_URL.

DESTRUCTIVE: wipes all data. Intended for resetting a fresh deployment that
has no real data yet.

Usage (PowerShell):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.reset_db
"""
from __future__ import annotations

from app.db.models import Base
from app.db.session import engine


def main() -> int:
    print(f"Resetting (drop + create) on: {engine.url.render_as_string(hide_password=True)}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("reset done. Tables present:")
    for name in sorted(Base.metadata.tables.keys()):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
