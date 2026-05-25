from datetime import date, datetime, timedelta

from app.db.models import CookingLog, Dish
from app.services.week import get_monday


def _dish(db_session, user_id, name, cook_count=0):
    d = Dish(user_id=user_id, name=name, main_ingredients=[], source="user_known", cook_count=cook_count)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _log(db_session, user_id, dish_id, when):
    db_session.add(CookingLog(user_id=user_id, dish_id=dish_id, meal_type="lunch", cooked_at=when))
    db_session.commit()


def test_history_empty(authed_client):
    r = authed_client.get("/api/history")
    assert r.status_code == 200
    assert r.json() == {"week_count": 0, "distinct_count": 0, "top_dishes": [], "recent": []}


def test_history_counts_and_rankings(authed_client, db_session, test_user):
    a = _dish(db_session, test_user.id, "番茄炒蛋", cook_count=5)
    b = _dish(db_session, test_user.id, "红烧肉", cook_count=3)
    now = datetime.utcnow()
    _log(db_session, test_user.id, a.id, now)
    _log(db_session, test_user.id, a.id, now - timedelta(hours=1))
    _log(db_session, test_user.id, b.id, now - timedelta(hours=2))
    r = authed_client.get("/api/history")
    body = r.json()
    assert body["week_count"] == 3
    assert body["distinct_count"] == 2
    assert body["top_dishes"][0] == {"name": "番茄炒蛋", "cook_count": 5}
    assert body["top_dishes"][1] == {"name": "红烧肉", "cook_count": 3}
    assert body["recent"][0]["name"] == "番茄炒蛋"
    assert len(body["recent"]) == 3


def test_history_isolation(authed_client, db_session, test_user, test_user_b):
    other = _dish(db_session, test_user_b.id, "别人的菜", cook_count=99)
    _log(db_session, test_user_b.id, other.id, datetime.utcnow())
    r = authed_client.get("/api/history")
    body = r.json()
    assert body["week_count"] == 0
    assert body["top_dishes"] == []


def test_history_requires_auth(client):
    r = client.get("/api/history")
    assert r.status_code == 401
