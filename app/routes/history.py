from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CookingLog, Dish, User
from app.db.session import get_db
from app.services.auth import current_user
from app.services.week import get_monday

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def get_history(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    week_start = datetime.combine(get_monday(date.today()), datetime.min.time())

    week_logs = list(
        db.scalars(
            select(CookingLog).where(
                CookingLog.user_id == user.id, CookingLog.cooked_at >= week_start
            )
        )
    )
    week_count = len(week_logs)
    distinct_count = len({lg.dish_id for lg in week_logs})

    top = db.execute(
        select(Dish.name, Dish.cook_count)
        .where(Dish.user_id == user.id, Dish.cook_count > 0)
        .order_by(Dish.cook_count.desc(), Dish.name)
        .limit(5)
    ).all()
    top_dishes = [{"name": name, "cook_count": cc} for name, cc in top]

    recent_rows = db.execute(
        select(Dish.name, CookingLog.meal_type, CookingLog.cooked_at)
        .join(Dish, Dish.id == CookingLog.dish_id)
        .where(CookingLog.user_id == user.id)
        .order_by(CookingLog.cooked_at.desc())
        .limit(10)
    ).all()
    recent = [
        {"name": name, "meal_type": meal, "cooked_at": ca.isoformat()}
        for name, meal, ca in recent_rows
    ]

    return {
        "week_count": week_count,
        "distinct_count": distinct_count,
        "top_dishes": top_dishes,
        "recent": recent,
    }
