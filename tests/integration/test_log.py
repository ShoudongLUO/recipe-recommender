from datetime import date

from app.db.models import CookingLog, Dish, WeeklyIngredients
from app.services.week import get_monday


def _seed_dish_and_ingredients(db_session, user_id):
    db_session.add(WeeklyIngredients(
        user_id=user_id, week_start=get_monday(date.today()), items=["a", "b"]
    ))
    d = Dish(user_id=user_id, name="X", main_ingredients=["a"], source="user_known", cook_count=0)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_log_known_dish_bumps_count(authed_client, db_session, test_user):
    d = _seed_dish_and_ingredients(db_session, test_user.id)
    r = authed_client.post("/api/log", json={"dish_id": d.id, "meal_type": "lunch"})
    assert r.status_code == 200
    db_session.expire_all()
    refreshed = db_session.get(Dish, d.id)
    assert refreshed.cook_count == 1
    logs = db_session.query(CookingLog).all()
    assert len(logs) == 1
    assert logs[0].user_id == test_user.id


def test_log_new_dish_added_to_library(authed_client, db_session, test_user):
    body = {
        "gemini_dish": {
            "name": "新菜A", "category": "主菜", "cuisine": "粤",
            "spicy": 0, "main_ingredients": ["虾"],
        },
        "meal_type": "dinner",
        "add_to_library": True,
    }
    r = authed_client.post("/api/log", json=body)
    assert r.status_code == 200
    dish = db_session.query(Dish).filter_by(name="新菜A").one()
    assert dish.source == "user_known"
    assert dish.cook_count == 1
    assert dish.user_id == test_user.id


def test_log_new_dish_not_added_stays_suggested(authed_client, db_session, test_user):
    body = {
        "gemini_dish": {
            "name": "新菜B", "category": "主菜", "cuisine": "粤",
            "spicy": 0, "main_ingredients": ["蛋"],
        },
        "meal_type": "dinner",
        "add_to_library": False,
    }
    r = authed_client.post("/api/log", json=body)
    assert r.status_code == 200
    dish = db_session.query(Dish).filter_by(name="新菜B").one()
    assert dish.source == "gemini_suggested"
    assert dish.cook_count == 1


def test_log_invalid_body_rejected(authed_client):
    r = authed_client.post("/api/log", json={"meal_type": "lunch"})
    assert r.status_code == 400


def test_log_cannot_target_other_users_dish(authed_client, db_session, test_user, test_user_b):
    """A cannot log a dish owned by B."""
    b_dish = Dish(user_id=test_user_b.id, name="B's dish", source="user_known")
    db_session.add(b_dish)
    db_session.commit()
    db_session.refresh(b_dish)

    r = authed_client.post("/api/log", json={"dish_id": b_dish.id, "meal_type": "lunch"})
    assert r.status_code == 404


def test_no_auth_returns_401(client):
    r = client.post("/api/log", json={"dish_id": 1, "meal_type": "lunch"})
    assert r.status_code == 401
