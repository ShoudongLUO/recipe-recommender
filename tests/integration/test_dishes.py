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


def _make_dish(db_session, user_id, name="红烧肉"):
    from app.db.models import Dish
    d = Dish(user_id=user_id, name=name, main_ingredients=["五花肉"], source="user_known", cook_count=0)
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_delete_dish_removes_dish_and_logs(authed_client, db_session, test_user):
    from app.db.models import CookingLog, Dish
    d = _make_dish(db_session, test_user.id)
    db_session.add(CookingLog(user_id=test_user.id, dish_id=d.id, meal_type="lunch"))
    db_session.commit()
    r = authed_client.delete(f"/api/dishes/{d.id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    db_session.expire_all()
    assert db_session.get(Dish, d.id) is None
    assert db_session.query(CookingLog).filter_by(dish_id=d.id).count() == 0


def test_delete_nonexistent_returns_404(authed_client):
    r = authed_client.delete("/api/dishes/99999")
    assert r.status_code == 404


def test_delete_other_users_dish_returns_404(authed_client, db_session, test_user_b):
    from app.db.models import Dish
    d = _make_dish(db_session, test_user_b.id, name="别人的菜")
    r = authed_client.delete(f"/api/dishes/{d.id}")
    assert r.status_code == 404
    db_session.expire_all()
    assert db_session.get(Dish, d.id) is not None


def test_delete_requires_auth(client, db_session, test_user):
    d = _make_dish(db_session, test_user.id)
    r = client.delete(f"/api/dishes/{d.id}")
    assert r.status_code == 401
