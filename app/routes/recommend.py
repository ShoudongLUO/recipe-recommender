from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import CookingLog, Dish, Profile, User, WeeklyIngredients
from app.db.session import get_db
from app.services.auth import current_user
from app.services.cache import recommend_cache
from app.services.filters import can_cook_with, has_forbidden
from app.services.llm.base import LLMUnavailable, LLMParseError
from app.services.llm import factory
from app.services.quota import bump_quota, today_quota
from app.services.scoring import score_dish
from app.services.week import get_monday

router = APIRouter(prefix="/api", tags=["recommend"])

MEAL_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


class RecommendIn(BaseModel):
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner)$")


def _dish_to_dict(d: Dish) -> dict:
    return {
        "id": d.id, "name": d.name, "category": d.category, "cuisine": d.cuisine,
        "main_ingredients": d.main_ingredients, "spicy": d.spicy,
        "source": d.source, "cook_count": d.cook_count,
    }


@router.post("/recommend")
def recommend(
    body: RecommendIn,
    db: Session = Depends(get_db),
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
        and (not d.suitable_meals or body.meal_type in d.suitable_meals)
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

    # Allow a new dish even if it needs up to this many ingredients not yet in
    # the pantry; surface those as a shopping hint instead of dropping the dish.
    MAX_MISSING = 2

    llm_failed = False
    if today_quota(db, user.id) >= settings.daily_gemini_quota:
        warning = "今日 AI 配额已用尽，明日恢复"
    else:
        try:
            raw_dishes, fell_back = factory.recommend_new_dishes(
                db, user,
                cuisine_prefs=profile.cuisine_prefs, spicy=profile.spicy, dislikes=profile.dislikes,
                ingredients=pantry, cuisine_histogram=cuisine_hist, cooked_this_week=cooked_names,
                meal_label=MEAL_LABELS[body.meal_type],
            )
            bump_quota(db, user.id)
            pantry_set = set(pantry)
            for d in raw_dishes:
                ings = d.get("main_ingredients", [])
                if has_forbidden(d.get("cuisine"), ings, profile.dislikes):
                    continue
                missing = [i for i in ings if i not in pantry_set]
                if len(missing) > 2:
                    continue
                new_dishes.append({
                    "name": d.get("name"), "category": d.get("category"), "cuisine": d.get("cuisine"),
                    "spicy": int(d.get("spicy", 0) or 0), "main_ingredients": ings,
                    "missing_ingredients": missing, "why_recommended": d.get("why_recommended", ""),
                    "source": "gemini_suggested",
                })
            if fell_back:
                warning = "今日 pro 额度已尽，已临时用 flash"
        except (LLMUnavailable, LLMParseError) as e:
            llm_failed = True
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                warning = "今日 AI 额度已用尽（免费层限制），明日恢复"
            elif "decrypt" in msg:
                warning = "保存的 AI key 无法读取（可能因为加密密钥已更换），请到「设置」重新输入"
            elif "timed out" in msg or "timeout" in msg.lower():
                warning = "AI 响应超时（服务较慢），请再点一次重试"
            elif "no LLM configured" in msg or "no api key" in msg:
                warning = "请先在「设置」里配置 AI（或暂无可用 key）"
            else:
                warning = "新菜推荐暂不可用"

    payload = {"known": known, "new": new_dishes, "warning": warning}
    # Do not cache transient LLM failures, otherwise a single timeout sticks for
    # the whole TTL and tapping the same meal returns the failure without retrying.
    if not llm_failed:
        recommend_cache.set(cache_key, payload)
    return payload


class GeminiDishPayload(BaseModel):
    name: str
    category: str | None = None
    cuisine: str | None = None
    spicy: int = 0
    main_ingredients: list[str] = Field(default_factory=list)


class LogIn(BaseModel):
    dish_id: int | None = None
    gemini_dish: GeminiDishPayload | None = None
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner)$")
    add_to_library: bool = False


@router.post("/log")
def log_dish(
    body: LogIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if body.dish_id is None and body.gemini_dish is None:
        raise HTTPException(status_code=400, detail="dish_id or gemini_dish required")

    if body.dish_id is not None:
        dish = db.scalar(
            select(Dish).where(Dish.id == body.dish_id, Dish.user_id == user.id)
        )
        if dish is None:
            raise HTTPException(status_code=404, detail="Dish not found")
        dish.cook_count += 1
    else:
        g = body.gemini_dish
        existing = db.scalar(
            select(Dish).where(Dish.user_id == user.id, Dish.name == g.name)
        )
        if existing:
            dish = existing
            if body.add_to_library and dish.source != "user_known":
                dish.source = "user_known"
            dish.cook_count += 1
        else:
            dish = Dish(
                user_id=user.id,
                name=g.name,
                category=g.category,
                cuisine=g.cuisine,
                main_ingredients=g.main_ingredients,
                spicy=g.spicy,
                tags=[],
                source="user_known" if body.add_to_library else "gemini_suggested",
                cook_count=1,
                needs_review=False,
            )
            db.add(dish)
            db.flush()

    db.add(CookingLog(user_id=user.id, dish_id=dish.id, meal_type=body.meal_type))
    db.commit()
    return {"ok": True, "dish_id": dish.id, "cook_count": dish.cook_count}
