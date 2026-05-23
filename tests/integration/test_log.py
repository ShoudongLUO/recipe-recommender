from datetime import date

from app.db.models import CookingLog, Dish, WeeklyIngredients
from app.services.week import get_monday


def _seed_dish_and_ingredients(db_session):
    db_session.add(WeeklyIngredients(week_start=get_monday(date.today()), items=["a", "b"]))
    d = Dish(name="X", main_ingredients=["a"], source="user_known", cook_count=0)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_log_known_dish_bumps_count(client, db_session):
    d = _seed_dish_and_ingredients(db_session)
    r = client.post("/api/log", json={"dish_id": d.id, "meal_type": "lunch"})
    assert r.status_code == 200
    db_session.expire_all()
    refreshed = db_session.get(Dish, d.id)
    assert refreshed.cook_count == 1
    logs = db_session.query(CookingLog).all()
    assert len(logs) == 1


def test_log_new_dish_added_to_library(client, db_session):
    body = {
        "gemini_dish": {
            "name": "新菜A", "category": "主菜", "cuisine": "粤",
            "spicy": 0, "main_ingredients": ["虾"],
        },
        "meal_type": "dinner",
        "add_to_library": True,
    }
    r = client.post("/api/log", json=body)
    assert r.status_code == 200
    dish = db_session.query(Dish).filter_by(name="新菜A").one()
    assert dish.source == "user_known"
    assert dish.cook_count == 1


def test_log_new_dish_not_added_stays_suggested(client, db_session):
    body = {
        "gemini_dish": {
            "name": "新菜B", "category": "主菜", "cuisine": "粤",
            "spicy": 0, "main_ingredients": ["蛋"],
        },
        "meal_type": "dinner",
        "add_to_library": False,
    }
    r = client.post("/api/log", json=body)
    assert r.status_code == 200
    dish = db_session.query(Dish).filter_by(name="新菜B").one()
    assert dish.source == "gemini_suggested"
    assert dish.cook_count == 1


def test_log_invalid_body_rejected(client):
    r = client.post("/api/log", json={"meal_type": "lunch"})
    assert r.status_code == 400
