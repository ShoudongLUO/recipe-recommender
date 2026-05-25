"""Backfill dishes.suitable_meals for existing rows using a category heuristic.

Does NOT call the LLM. Run AFTER scripts.migrate_add_meals on an existing DB.

Heuristic:
    饮品            -> ["breakfast"]
    汤类/主菜/西餐   -> ["lunch", "dinner"]
    素食/其它/None  -> ["breakfast", "lunch", "dinner"]

Usage (PowerShell, Neon Postgres):
    $env:DATABASE_URL = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    python -m scripts.backfill_meals
"""
from __future__ import annotations

from app.db.models import Dish
from app.db.session import SessionLocal

ALL_MEALS = ["breakfast", "lunch", "dinner"]
_CATEGORY_MEALS = {
    "饮品": ["breakfast"],
    "汤类": ["lunch", "dinner"],
    "主菜": ["lunch", "dinner"],
    "西餐": ["lunch", "dinner"],
}


def meals_for_category(category: str | None) -> list[str]:
    return _CATEGORY_MEALS.get(category or "", ALL_MEALS)


def main() -> int:
    db = SessionLocal()
    try:
        n = 0
        for d in db.query(Dish).all():
            if not d.suitable_meals:
                d.suitable_meals = meals_for_category(d.category)
                n += 1
        db.commit()
        print(f"backfilled {n} dishes")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
