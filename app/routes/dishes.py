from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dish
from app.db.session import get_db
from app.services.gemini import GeminiClient, GeminiParseError, GeminiUnavailable

router = APIRouter(prefix="/api/dishes", tags=["dishes"])


class DishIn(BaseModel):
    name: str


class DishOut(BaseModel):
    id: int
    name: str
    category: str | None
    cuisine: str | None
    main_ingredients: list[str]
    spicy: int
    tags: list[str]
    source: str
    cook_count: int
    needs_review: bool


def _to_out(d: Dish) -> DishOut:
    return DishOut(
        id=d.id, name=d.name, category=d.category, cuisine=d.cuisine,
        main_ingredients=d.main_ingredients, spicy=d.spicy, tags=d.tags,
        source=d.source, cook_count=d.cook_count, needs_review=d.needs_review,
    )


def get_gemini(request: Request) -> GeminiClient:
    return request.app.state.gemini


@router.get("", response_model=list[DishOut])
def list_dishes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Dish).order_by(Dish.created_at.desc())).all()
    return [_to_out(d) for d in rows]


@router.post("", response_model=DishOut, status_code=status.HTTP_201_CREATED)
def add_dish(
    body: DishIn,
    db: Session = Depends(get_db),
    gemini: GeminiClient = Depends(get_gemini),
):
    existing = db.scalar(select(Dish).where(Dish.name == body.name))
    if existing:
        raise HTTPException(status_code=409, detail="Dish already exists")

    classified: dict = {}
    needs_review = False
    try:
        classified = gemini.classify_dish(body.name)
    except (GeminiUnavailable, GeminiParseError):
        needs_review = True

    d = Dish(
        name=body.name,
        category=classified.get("category"),
        cuisine=classified.get("cuisine"),
        main_ingredients=classified.get("main_ingredients", []) or [],
        spicy=int(classified.get("spicy", 0) or 0),
        tags=classified.get("tags", []) or [],
        source="user_known",
        cook_count=0,
        needs_review=needs_review,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _to_out(d)
