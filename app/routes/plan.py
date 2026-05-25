from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Dish, Profile, User
from app.db.session import get_db
from app.services.auth import current_user
from app.services.filters import has_forbidden
from app.services.llm import factory
from app.services.llm.base import LLMParseError, LLMUnavailable
from app.services.quota import bump_quota, today_quota
from app.services.scoring import score_dish

router = APIRouter(prefix="/api/plan", tags=["plan"])

MAX_KNOWN = 8
AI_COUNT = 4
TOTAL = 10


def compose_candidates(
    known_dicts: list[dict], ai_dicts: list[dict], limit: int = TOTAL
) -> list[dict]:
    """known 在前（调用方已排序），ai 去掉与 known 重名的，合并截断到 limit。"""
    known_names = {d["name"] for d in known_dicts}
    ai_unique = [d for d in ai_dicts if d["name"] not in known_names]
    return (known_dicts + ai_unique)[:limit]


def _known_to_candidate(d: Dish) -> dict:
    return {
        "id": d.id, "name": d.name, "category": d.category, "cuisine": d.cuisine,
        "spicy": d.spicy, "main_ingredients": d.main_ingredients,
        "source": "known", "why_recommended": None,
    }


def _ai_to_candidate(d: dict) -> dict:
    return {
        "id": None, "name": d.get("name"), "category": d.get("category"),
        "cuisine": d.get("cuisine"), "spicy": int(d.get("spicy", 0) or 0),
        "main_ingredients": d.get("main_ingredients", []) or [],
        "source": "ai", "why_recommended": d.get("why_recommended", ""),
    }


@router.post("/candidates")
def candidates(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    profile = db.get(Profile, user.id)
    all_known = list(
        db.scalars(select(Dish).where(Dish.user_id == user.id, Dish.source == "user_known"))
    )
    eligible = [
        d for d in all_known
        if not has_forbidden(d.cuisine, d.main_ingredients, profile.dislikes)
    ]
    eligible.sort(key=lambda d: score_dish(d, profile), reverse=True)
    known_dicts = [_known_to_candidate(d) for d in eligible[:MAX_KNOWN]]

    ai_dicts: list[dict] = []
    ai_warning: str | None = None
    if today_quota(db, user.id) >= settings.daily_gemini_quota:
        ai_warning = "今日 AI 配额已用尽，仅从会做的菜推荐"
    else:
        try:
            raw, _fell = factory.plan_new_dishes(
                db, user,
                cuisine_prefs=profile.cuisine_prefs, spicy=profile.spicy,
                dislikes=profile.dislikes,
                known_names=[d.name for d in all_known], count=AI_COUNT,
            )
            bump_quota(db, user.id)
            for d in raw:
                if has_forbidden(d.get("cuisine"), d.get("main_ingredients", []) or [], profile.dislikes):
                    continue
                ai_dicts.append(_ai_to_candidate(d))
        except (LLMUnavailable, LLMParseError):
            ai_warning = "AI 新菜暂时没取到，可只从会做的菜里挑"

    return {
        "candidates": compose_candidates(known_dicts, ai_dicts, limit=TOTAL),
        "ai_warning": ai_warning,
    }
