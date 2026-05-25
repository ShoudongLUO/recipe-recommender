"""Add dishes.recipe column to an existing database (idempotent).

Usage (PowerShell, Neon):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.migrate_add_recipe
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def main() -> int:
    print(f"Ensuring recipe column on: {engine.url.render_as_string(hide_password=True)}")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE dishes ADD COLUMN IF NOT EXISTS recipe TEXT DEFAULT ''"))
    print("recipe column ensured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
