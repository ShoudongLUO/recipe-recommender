from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ApiQuota, CookingLog, Dish, Profile, User, WeeklyIngredients
from app.db.session import get_db
from app.services.auth import current_user
from app.services.cache import recommend_cache
from app.services.filters import can_cook_with, has_forbidden
from app.services.gemini import GeminiClient, GeminiParseError, GeminiUnavailable
from app.services.scoring import score_dish
from app.services.week import get_monday

router = APIRouter(prefix="/api", tags=["recommend"])


class RecommendIn(BaseModel):
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner)$")


def get_gemini(request: Request) -> GeminiClient:
    return request.app.state.gemini


def _dish_to_dict(d: Dish) -> dict:
    return {
        "id": d.id, "name": d.name, "category": d.category, "cuisine": d.cuisine,
        "main_ingredients": d.main_ingredients, "spicy": d.spicy,
        "source": d.source, "cook_count": d.cook_count,
    }


def _bump_quota(db: Session, user_id) -> int:
    today = date.today()
    row = db.get(ApiQuota, (user_id, today))
    if row is None:
        row = ApiQuota(user_id=user_id, quota_date=today, count=1)
        db.add(row)
    else:
        row.count += 1
    db.commit()
    return row.count


def _today_quota(db: Session, user_id) -> int:
    row = db.get(ApiQuota, (user_id, date.today()))
    return row.count if row else 0


@router.post("/recommend")
def recommend(
    body: RecommendIn,
    db: Session = Depends(get_db),
    gemini: GeminiClient = Depends(get_gemini),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    profile = db.get(Profile, user.id)
    ws = get_monday(date.today())
    week = db.scalar(
        select(WeeklyIngredients).where(
            WeeklyIngredients.user_id == user.id,
            WeeklyIngredients.week_start == ws,
        )
    )
    if week is None or not week.items:
        return {"error": "INGREDIENTS_EMPTY"}

    cooked_ids = {
        row.dish_id for row in db.scalars(
            select(CookingLog).where(
                CookingLog.user_id == user.id,
                CookingLog.cooked_at >= datetime.combine(ws, datetime.min.time()),
            )
        )
    }
    all_dishes: list[Dish] = list(
        db.scalars(select(Dish).where(Dish.user_id == user.id))
    )

    cache_key = f"{user.id}:{body.meal_type}"
    cached = recommend_cache.get(cache_key)
    if cached is not None:
        return cached

    pantry = week.items
    candidates = [
        d for d in all_dishes
        if d.source == "user_known"
        and d.id not in cooked_ids
        and can_cook_with(d.main_ingredients, pantry)
        and not has_forbidden(d.cuisine, d.main_ingredients, profile.dislikes)
    ]
    candidates.sort(key=lambda d: score_dish(d, profile), reverse=True)
    known = [_dish_to_dict(d) for d in candidates[:2]]

    warning: str | None = None
    new_dishes: list[dict] = []
    cooked_names = [d.name for d in all_dishes if d.id in cooked_ids]
    cuisine_hist: dict[str, int] = {}
    for d in all_dishes:
        if d.cuisine:
            cuisine_hist[d.cuisine] = cuisine_hist.get(d.cuisine, 0) + 1

    if _today_quota(db, user.id) >= settings.daily_gemini_quota:
        warning = "今日 AI 配额已用尽，明日恢复"
    elif not gemini.available:
        warning = "新菜推荐暂不可用"
    else:
        try:
            raw_dishes = gemini.generate_new_dishes(
                cuisine_prefs=profile.cuisine_prefs,
                spicy=profile.spicy,
                dislikes=profile.dislikes,
                ingredients=pantry,
                cuisine_histogram=cuisine_hist,
                cooked_this_week=cooked_names,
            )
            _bump_quota(db, user.id)
            for d in raw_dishes:
                ings = d.get("main_ingredients", [])
                if not can_cook_with(ings, pantry):
                    continue
                if has_forbidden(d.get("cuisine"), ings, profile.dislikes):
                    continue
                new_dishes.append({
                    "name": d.get("name"),
                    "category": d.get("category"),
                    "cuisine": d.get("cuisine"),
                    "spicy": int(d.get("spicy", 0) or 0),
                    "main_ingredients": ings,
                    "why_recommended": d.get("why_recommended", ""),
                    "source": "gemini_suggested",
                })
        except (GeminiUnavailable, GeminiParseError):
            warning = "新菜推荐暂不可用"

    payload = {"known": known, "new": new_dishes, "warning": warning}
    recommend_cache.set(cache_key, payload)
    return payload
