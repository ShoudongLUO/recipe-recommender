"""Add weekly_ingredients.quantities and used_up columns (idempotent).

Usage (PowerShell, Neon):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.migrate_add_quantities
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def main() -> int:
    print(f"Ensuring quantity columns on: {engine.url.render_as_string(hide_password=True)}")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE weekly_ingredients ADD COLUMN IF NOT EXISTS quantities JSON DEFAULT '{}'"))
        conn.execute(text("ALTER TABLE weekly_ingredients ADD COLUMN IF NOT EXISTS used_up JSON DEFAULT '[]'"))
    print("quantity columns ensured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
