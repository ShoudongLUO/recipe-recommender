from app.services.auth import create_token


def test_get_empty_returns_none(authed_client):
    r = authed_client.get("/api/ingredients")
    assert r.status_code == 200
    assert r.json() == {"week_start": None, "items": [], "quantities": {}, "used_up": []}


def test_put_creates_then_get(authed_client):
    r = authed_client.put("/api/ingredients", json={"items": ["番茄", "鸡蛋", "猪肉"]})
    assert r.status_code == 200
    assert r.json()["items"] == ["番茄", "鸡蛋", "猪肉"]
    assert r.json()["week_start"] is not None

    r2 = authed_client.get("/api/ingredients")
    assert r2.json()["items"] == ["番茄", "鸡蛋", "猪肉"]


def test_put_twice_same_week_overwrites(authed_client):
    authed_client.put("/api/ingredients", json={"items": ["a"]})
    authed_client.put("/api/ingredients", json={"items": ["b", "c"]})
    r = authed_client.get("/api/ingredients")
    assert r.json()["items"] == ["b", "c"]


def test_ingredients_isolation(authed_client, test_user, test_user_b):
    a_token = create_token(user_id=test_user.id, username=test_user.username)
    authed_client.headers.update({"Authorization": f"Bearer {a_token}"})
    authed_client.put("/api/ingredients", json={"items": ["番茄", "鸡蛋"]})

    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    r = authed_client.get("/api/ingredients")
    assert r.json()["items"] == []


def test_no_auth_returns_401(client):
    r = client.get("/api/ingredients")
    assert r.status_code == 401


def test_put_get_quantities_and_used_up(authed_client):
    r = authed_client.put("/api/ingredients", json={
        "items": ["番茄", "鸡蛋"], "quantities": {"番茄": "2个"}, "used_up": ["鸡蛋"]})
    assert r.status_code == 200
    g = authed_client.get("/api/ingredients").json()
    assert g["items"] == ["番茄", "鸡蛋"]
    assert g["quantities"] == {"番茄": "2个"}
    assert g["used_up"] == ["鸡蛋"]


def test_put_prunes_orphan_quantities_and_used_up(authed_client):
    r = authed_client.put("/api/ingredients", json={
        "items": ["番茄"], "quantities": {"番茄": "2个", "旧菜": "x"}, "used_up": ["旧菜"]})
    b = r.json()
    assert b["quantities"] == {"番茄": "2个"}
    assert b["used_up"] == []


def test_get_carries_over_from_prev_week(authed_client, db_session, test_user):
    from datetime import date, timedelta
    from app.db.models import WeeklyIngredients
    from app.services.week import get_monday
    db_session.add(WeeklyIngredients(
        user_id=test_user.id, week_start=get_monday(date.today()) - timedelta(days=7),
        items=["番茄", "鸡蛋"], quantities={"番茄": "2个"}, used_up=["鸡蛋"]))
    db_session.commit()
    g = authed_client.get("/api/ingredients").json()
    assert g["items"] == ["番茄"]
    assert g["quantities"] == {"番茄": "2个"}
    assert g["used_up"] == []
