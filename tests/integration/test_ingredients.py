from app.services.auth import create_token


def test_get_empty_returns_none(authed_client):
    r = authed_client.get("/api/ingredients")
    assert r.status_code == 200
    assert r.json() == {"week_start": None, "items": []}


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
