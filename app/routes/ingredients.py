from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, WeeklyIngredients
from app.db.session import get_db
from app.services.auth import current_user
from app.services.cache import recommend_cache
from app.services.pantry import ensure_current_week
from app.services.week import get_monday

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


class IngredientsIn(BaseModel):
    items: list[str]
    quantities: dict[str, str] = {}
    used_up: list[str] = []


class IngredientsOut(BaseModel):
    week_start: date | None
    items: list[str]
    quantities: dict[str, str]
    used_up: list[str]


@router.get("", response_model=IngredientsOut)
def get_ingredients(db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = ensure_current_week(db, user)
    if row is None:
        return IngredientsOut(week_start=None, items=[], quantities={}, used_up=[])
    return IngredientsOut(
        week_start=row.week_start, items=row.items,
        quantities=row.quantities or {}, used_up=row.used_up or [],
    )


@router.put("", response_model=IngredientsOut)
def put_ingredients(
    body: IngredientsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = get_monday(date.today())
    row = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    item_set = set(body.items)
    quantities = {n: q for n, q in body.quantities.items() if n in item_set}
    used_up = [n for n in body.used_up if n in item_set]
    if row is None:
        row = WeeklyIngredients(
            user_id=user.id, week_start=ws, items=body.items,
            quantities=quantities, used_up=used_up,
        )
        db.add(row)
    else:
        row.items = body.items
        row.quantities = quantities
        row.used_up = used_up
        row.updated_at = datetime.utcnow()
    db.commit()
    # Pantry changed (items/used_up) -> drop stale cached recommendations for this user.
    recommend_cache.invalidate_prefix(f"{user.id}:")
    return IngredientsOut(week_start=ws, items=body.items, quantities=quantities, used_up=used_up)
