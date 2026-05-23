from __future__ import annotations

import json
from datetime import date, datetime

from app.db.models import CookingLog, Dish, WeeklyIngredients
from app.services.week import get_monday


def _seed_ingredients(db_session, items):
    db_session.add(WeeklyIngredients(week_start=get_monday(date.today()), items=items))
    db_session.commit()


def _seed_dish(db_session, **kw) -> Dish:
    d = Dish(
        name=kw["name"],
        category=kw.get("category", "主菜"),
        cuisine=kw.get("cuisine", "家常"),
        main_ingredients=kw.get("main_ingredients", []),
        spicy=kw.get("spicy", 0),
        tags=[],
        source=kw.get("source", "user_known"),
        cook_count=kw.get("cook_count", 0),
        needs_review=False,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_no_ingredients_returns_error(client):
    r = client.post("/api/recommend", json={"meal_type": "dinner"})
    assert r.status_code == 200
    assert r.json() == {"error": "INGREDIENTS_EMPTY"}


def test_known_branch_filters_and_sorts(client, db_session, fake_transport):
    _seed_ingredients(db_session, ["番茄", "鸡蛋", "猪肉"])
    _seed_dish(db_session, name="A", main_ingredients=["番茄", "鸡蛋"], cook_count=5)
    _seed_dish(db_session, name="B", main_ingredients=["番茄", "鸡蛋"], cook_count=0)
    _seed_dish(db_session, name="C", main_ingredients=["羊肉"], cook_count=10)
    fake_transport.push(json.dumps({"dishes": [
        {"name": "番茄牛肉汤", "category": "汤类", "cuisine": "粤",
         "spicy": 0, "main_ingredients": ["番茄", "猪肉"], "why_recommended": "y"},
        {"name": "鸡蛋羹", "category": "主菜", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["鸡蛋"], "why_recommended": "y"},
    ]}))
    r = client.post("/api/recommend", json={"meal_type": "lunch"})
    body = r.json()
    known_names = [d["name"] for d in body["known"]]
    assert known_names[0] == "A"
    assert "C" not in known_names
    assert len(body["new"]) == 2


def test_dislike_excludes_dish(client, db_session, fake_transport):
    client.put("/api/profile", json={"cuisine_prefs": [], "spicy": 2, "dislikes": ["香菜"]})
    _seed_ingredients(db_session, ["香菜", "牛肉"])
    _seed_dish(db_session, name="香菜牛肉", main_ingredients=["香菜", "牛肉"])
    fake_transport.push(json.dumps({"dishes": []}))
    r = client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r.json()["known"] == []


def test_already_cooked_this_week_excluded(client, db_session, fake_transport):
    _seed_ingredients(db_session, ["番茄", "鸡蛋"])
    d = _seed_dish(db_session, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    db_session.add(CookingLog(dish_id=d.id, meal_type="lunch", cooked_at=datetime.utcnow()))
    db_session.commit()
    fake_transport.push(json.dumps({"dishes": []}))
    r = client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r.json()["known"] == []


def test_gemini_failure_returns_warning(client, db_session, fake_transport):
    _seed_ingredients(db_session, ["番茄", "鸡蛋"])
    _seed_dish(db_session, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    fake_transport.push(RuntimeError("network"))
    r = client.post("/api/recommend", json={"meal_type": "lunch"})
    body = r.json()
    assert body["new"] == []
    assert body["warning"] == "新菜推荐暂不可用"
    assert len(body["known"]) == 1


def test_new_dish_filtered_when_ingredient_missing(client, db_session, fake_transport):
    _seed_ingredients(db_session, ["番茄"])
    fake_transport.push(json.dumps({"dishes": [
        {"name": "番茄汤", "category": "汤类", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["番茄"], "why_recommended": "y"},
        {"name": "牛排", "category": "西餐", "cuisine": "意式",
         "spicy": 0, "main_ingredients": ["牛排"], "why_recommended": "y"},
    ]}))
    r = client.post("/api/recommend", json={"meal_type": "dinner"})
    new_names = [d["name"] for d in r.json()["new"]]
    assert "番茄汤" in new_names
    assert "牛排" not in new_names


def test_cache_hit_avoids_second_gemini_call(client, db_session, fake_transport):
    _seed_ingredients(db_session, ["番茄"])
    fake_transport.push(json.dumps({"dishes": [
        {"name": "番茄汤", "category": "汤类", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["番茄"], "why_recommended": "y"},
    ]}))
    r1 = client.post("/api/recommend", json={"meal_type": "lunch"})
    r2 = client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r1.json() == r2.json()
    assert len(fake_transport.calls) == 1
