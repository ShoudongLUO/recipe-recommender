import json
from datetime import date, datetime

from app.db.models import CookingLog, Dish, WeeklyIngredients
from app.services.auth import create_token
from app.services.llm.base import LLMUnavailable
from app.services.week import get_monday


def _seed_ingredients(db_session, user_id, items):
    db_session.add(WeeklyIngredients(
        user_id=user_id, week_start=get_monday(date.today()), items=items
    ))
    db_session.commit()


def _seed_dish(db_session, user_id, **kw) -> Dish:
    d = Dish(
        user_id=user_id,
        name=kw["name"],
        category=kw.get("category", "主菜"),
        cuisine=kw.get("cuisine", "家常"),
        main_ingredients=kw.get("main_ingredients", []),
        spicy=kw.get("spicy", 0),
        tags=[],
        source=kw.get("source", "user_known"),
        cook_count=kw.get("cook_count", 0),
        needs_review=False,
        suitable_meals=kw.get("suitable_meals", []),
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_no_ingredients_returns_error(authed_client):
    r = authed_client.post("/api/recommend", json={"meal_type": "dinner"})
    assert r.status_code == 200
    assert r.json() == {"error": "INGREDIENTS_EMPTY"}


def test_known_branch_filters_and_sorts(authed_client, db_session, fake_llm, test_user):
    _seed_ingredients(db_session, test_user.id, ["番茄", "鸡蛋", "猪肉"])
    _seed_dish(db_session, test_user.id, name="A", main_ingredients=["番茄", "鸡蛋"], cook_count=5)
    _seed_dish(db_session, test_user.id, name="B", main_ingredients=["番茄", "鸡蛋"], cook_count=0)
    _seed_dish(db_session, test_user.id, name="C", main_ingredients=["羊肉"], cook_count=10)
    fake_llm.new_dishes_queue.append([
        {"name": "番茄牛肉汤", "category": "汤类", "cuisine": "粤",
         "spicy": 0, "main_ingredients": ["番茄", "猪肉"], "why_recommended": "y"},
        {"name": "鸡蛋羹", "category": "主菜", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["鸡蛋"], "why_recommended": "y"},
    ])
    r = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    body = r.json()
    known_names = [d["name"] for d in body["known"]]
    assert known_names[0] == "A"
    assert "C" not in known_names
    assert len(body["new"]) == 2


def test_dislike_excludes_dish(authed_client, db_session, fake_llm, test_user):
    authed_client.put("/api/profile", json={"cuisine_prefs": [], "spicy": 2, "dislikes": ["香菜"]})
    _seed_ingredients(db_session, test_user.id, ["香菜", "牛肉"])
    _seed_dish(db_session, test_user.id, name="香菜牛肉", main_ingredients=["香菜", "牛肉"])
    fake_llm.new_dishes_queue.append([])
    r = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r.json()["known"] == []


def test_already_cooked_this_week_excluded(authed_client, db_session, fake_llm, test_user):
    _seed_ingredients(db_session, test_user.id, ["番茄", "鸡蛋"])
    d = _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    db_session.add(CookingLog(
        user_id=test_user.id, dish_id=d.id, meal_type="lunch", cooked_at=datetime.utcnow()
    ))
    db_session.commit()
    fake_llm.new_dishes_queue.append([])
    r = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r.json()["known"] == []


def test_gemini_failure_returns_warning(authed_client, db_session, fake_llm, test_user):
    _seed_ingredients(db_session, test_user.id, ["番茄", "鸡蛋"])
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    fake_llm.new_dishes_queue.append(LLMUnavailable("network"))
    r = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    body = r.json()
    assert body["new"] == []
    assert body["warning"] == "新菜推荐暂不可用"
    assert len(body["known"]) == 1


def test_new_dish_missing_ingredients_annotated_or_dropped(authed_client, db_session, fake_llm, test_user):
    """New dishes needing <=2 missing ingredients are kept with a shopping hint;
    those needing 3+ are dropped."""
    _seed_ingredients(db_session, test_user.id, ["番茄", "鸡蛋"])
    fake_llm.new_dishes_queue.append([
        {"name": "番茄炒蛋", "category": "主菜", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["番茄", "鸡蛋"], "why_recommended": "y"},
        {"name": "番茄牛肉", "category": "主菜", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["番茄", "牛肉"], "why_recommended": "y"},
        {"name": "佛跳墙", "category": "汤类", "cuisine": "闽",
         "spicy": 0, "main_ingredients": ["鲍鱼", "海参", "瑶柱", "花胶"], "why_recommended": "y"},
    ])
    r = authed_client.post("/api/recommend", json={"meal_type": "dinner"})
    new = {d["name"]: d for d in r.json()["new"]}
    # fully available: kept, no missing
    assert "番茄炒蛋" in new
    assert new["番茄炒蛋"]["missing_ingredients"] == []
    # one missing (牛肉): kept with shopping hint
    assert "番茄牛肉" in new
    assert new["番茄牛肉"]["missing_ingredients"] == ["牛肉"]
    # four missing: dropped
    assert "佛跳墙" not in new


def test_cache_hit_avoids_second_gemini_call(authed_client, db_session, fake_llm, test_user):
    _seed_ingredients(db_session, test_user.id, ["番茄"])
    fake_llm.new_dishes_queue.append([
        {"name": "番茄汤", "category": "汤类", "cuisine": "家常",
         "spicy": 0, "main_ingredients": ["番茄"], "why_recommended": "y"},
    ])
    r1 = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    r2 = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r1.json() == r2.json()
    assert fake_llm.new_calls == 1


def test_recommend_isolation(authed_client, db_session, fake_llm, test_user, test_user_b):
    """User A's seeded ingredients/dishes should not appear in user B's recommendation."""
    _seed_ingredients(db_session, test_user.id, ["番茄", "鸡蛋"])
    _seed_dish(db_session, test_user.id, name="A's dish", main_ingredients=["番茄", "鸡蛋"])

    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    r = authed_client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r.json() == {"error": "INGREDIENTS_EMPTY"}


def test_no_auth_returns_401(client):
    r = client.post("/api/recommend", json={"meal_type": "lunch"})
    assert r.status_code == 401


def test_known_dishes_filtered_by_meal(authed_client, db_session, fake_llm, test_user):
    _seed_ingredients(db_session, test_user.id, ["大米", "鸡蛋", "猪肉"])
    # breakfast-only dish, dinner-only dish, and an unlabeled (all-meals) dish
    _seed_dish(db_session, test_user.id, name="白粥", main_ingredients=["大米"],
               suitable_meals=["breakfast"])
    _seed_dish(db_session, test_user.id, name="红烧肉", main_ingredients=["猪肉"],
               suitable_meals=["lunch", "dinner"])
    _seed_dish(db_session, test_user.id, name="炒蛋", main_ingredients=["鸡蛋"],
               suitable_meals=[])  # unlabeled -> visible for all meals
    fake_llm.new_dishes_queue.append([])
    r = authed_client.post("/api/recommend", json={"meal_type": "breakfast"})
    names = [d["name"] for d in r.json()["known"]]
    assert "白粥" in names
    assert "红烧肉" not in names   # dinner-only, hidden at breakfast
    assert "炒蛋" in names         # empty suitable_meals = all meals
