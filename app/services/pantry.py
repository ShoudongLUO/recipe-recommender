from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, WeeklyIngredients
from app.services.week import get_monday


def ensure_current_week(db: Session, user: User) -> WeeklyIngredients | None:
    """Return the current week's row; if absent, carry over the not-used-up
    items + quantities from the most recent prior week (used_up reset). Returns
    None when there's no prior data to carry."""
    ws = get_monday(date.today())
    row = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    if row is not None:
        return row
    prev = db.scalar(
        select(WeeklyIngredients)
        .where(WeeklyIngredients.user_id == user.id, WeeklyIngredients.week_start < ws)
        .order_by(WeeklyIngredients.week_start.desc())
    )
    if prev is None or not prev.items:
        return None
    used = set(prev.used_up or [])
    kept = [n for n in prev.items if n not in used]
    if not kept:
        return None
    qty = {n: v for n, v in (prev.quantities or {}).items() if n in kept}
    row = WeeklyIngredients(
        user_id=user.id, week_start=ws, items=kept, quantities=qty, used_up=[]
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
