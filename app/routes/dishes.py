from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CookingLog, Dish, User
from app.db.session import get_db
from app.services.auth import current_user
from app.services.llm.base import LLMUnavailable, LLMParseError
from app.services.llm import factory

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


@router.get("", response_model=list[DishOut])
def list_dishes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(
        select(Dish).where(Dish.user_id == user.id).order_by(Dish.created_at.desc())
    ).all()
    return [_to_out(d) for d in rows]


@router.post("", response_model=DishOut, status_code=status.HTTP_201_CREATED)
def add_dish(
    body: DishIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    existing = db.scalar(
        select(Dish).where(Dish.user_id == user.id, Dish.name == body.name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Dish already exists")

    classified: dict = {}
    needs_review = False
    try:
        classified = factory.classify_with_fallback(db, user, body.name)
    except (LLMUnavailable, LLMParseError):
        needs_review = True

    d = Dish(
        user_id=user.id,
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


@router.delete("/{dish_id}")
def delete_dish(
    dish_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    dish = db.scalar(select(Dish).where(Dish.id == dish_id, Dish.user_id == user.id))
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    db.execute(delete(CookingLog).where(CookingLog.dish_id == dish_id, CookingLog.user_id == user.id))
    db.delete(dish)
    db.commit()
    return {"ok": True}


class DishEdit(BaseModel):
    name: str
    category: str | None = None
    cuisine: str | None = None
    main_ingredients: list[str] = []
    spicy: int = 0
    tags: list[str] = []


@router.put("/{dish_id}", response_model=DishOut)
def edit_dish(
    dish_id: int,
    body: DishEdit,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    dish = db.scalar(select(Dish).where(Dish.id == dish_id, Dish.user_id == user.id))
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    dish.name = body.name
    dish.category = body.category
    dish.cuisine = body.cuisine
    dish.main_ingredients = body.main_ingredients
    dish.spicy = body.spicy
    dish.tags = body.tags
    dish.needs_review = False
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="已有同名菜")
    db.refresh(dish)
    return _to_out(dish)
