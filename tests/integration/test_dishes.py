import json

from app.services.auth import create_token


def _seed_classify(fake_transport, ingredients=None):
    fake_transport.push(json.dumps({
        "category": "主菜", "cuisine": "家常",
        "main_ingredients": ingredients or ["番茄", "鸡蛋"],
        "spicy": 0, "tags": ["炒"],
    }))


def test_add_dish_gemini_ok(authed_client, fake_transport):
    _seed_classify(fake_transport)
    r = authed_client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "番茄炒蛋"
    assert d["main_ingredients"] == ["番茄", "鸡蛋"]
    assert d["needs_review"] is False
    assert d["source"] == "user_known"


def test_add_dish_gemini_fails_marks_review(authed_client, fake_transport):
    fake_transport.push("garbage output")
    fake_transport.push("more garbage")
    r = authed_client.post("/api/dishes", json={"name": "怪菜"})
    assert r.status_code == 201
    d = r.json()
    assert d["needs_review"] is True
    assert d["main_ingredients"] == []


def test_add_duplicate_name_same_user_rejected(authed_client, fake_transport):
    _seed_classify(fake_transport)
    authed_client.post("/api/dishes", json={"name": "X"})
    _seed_classify(fake_transport)
    r = authed_client.post("/api/dishes", json={"name": "X"})
    assert r.status_code == 409


def test_two_users_can_each_have_same_dish_name(authed_client, fake_transport, test_user, test_user_b):
    """Same dish name OK across users; per-user uniqueness."""
    a_token = create_token(user_id=test_user.id, username=test_user.username)
    authed_client.headers.update({"Authorization": f"Bearer {a_token}"})
    _seed_classify(fake_transport)
    r1 = authed_client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r1.status_code == 201

    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    _seed_classify(fake_transport)
    r2 = authed_client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r2.status_code == 201


def test_list_dishes_isolation(authed_client, fake_transport, test_user, test_user_b):
    a_token = create_token(user_id=test_user.id, username=test_user.username)
    authed_client.headers.update({"Authorization": f"Bearer {a_token}"})
    _seed_classify(fake_transport, ingredients=["虾"])
    authed_client.post("/api/dishes", json={"name": "白灼虾"})

    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    r = authed_client.get("/api/dishes")
    assert r.json() == []


def test_no_auth_returns_401(client):
    r = client.get("/api/dishes")
    assert r.status_code == 401
