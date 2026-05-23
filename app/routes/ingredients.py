from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, WeeklyIngredients
from app.db.session import get_db
from app.services.auth import current_user
from app.services.week import get_monday

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


class IngredientsIn(BaseModel):
    items: list[str]


class IngredientsOut(BaseModel):
    week_start: date | None
    items: list[str]


@router.get("", response_model=IngredientsOut)
def get_ingredients(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ws = get_monday(date.today())
    row = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    if row is None:
        return IngredientsOut(week_start=None, items=[])
    return IngredientsOut(week_start=row.week_start, items=row.items)


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
    if row is None:
        row = WeeklyIngredients(user_id=user.id, week_start=ws, items=body.items)
        db.add(row)
    else:
        row.items = body.items
        row.updated_at = datetime.utcnow()
    db.commit()
    return IngredientsOut(week_start=ws, items=body.items)
