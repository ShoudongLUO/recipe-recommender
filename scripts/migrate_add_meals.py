"""Add the dishes.suitable_meals column to an existing database (idempotent).

Run BEFORE scripts.backfill_meals on a database that predates the
suitable_meals column. create_all does not ALTER existing tables.

Usage (PowerShell, Neon Postgres):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.migrate_add_meals
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def main() -> int:
    print(f"Ensuring suitable_meals column on: {engine.url.render_as_string(hide_password=True)}")
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE dishes ADD COLUMN IF NOT EXISTS suitable_meals JSON DEFAULT '[]'")
        )
    print("suitable_meals column ensured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
