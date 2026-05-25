from app.services.auth import create_token
from app.services.llm.base import LLMParseError


def _seed_classify(fake_llm, ingredients=None):
    fake_llm.classify_queue.append({
        "category": "主菜", "cuisine": "家常",
        "main_ingredients": ingredients or ["番茄", "鸡蛋"],
        "spicy": 0, "tags": ["炒"], "suitable_meals": ["lunch", "dinner"],
    })


def test_add_dish_gemini_ok(authed_client, fake_llm):
    _seed_classify(fake_llm)
    r = authed_client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "番茄炒蛋"
    assert d["main_ingredients"] == ["番茄", "鸡蛋"]
    assert d["needs_review"] is False
    assert d["source"] == "user_known"


def test_add_dish_gemini_fails_marks_review(authed_client, fake_llm):
    fake_llm.classify_queue.append(LLMParseError("bad"))
    r = authed_client.post("/api/dishes", json={"name": "怪菜"})
    assert r.status_code == 201
    d = r.json()
    assert d["needs_review"] is True
    assert d["main_ingredients"] == []


def test_add_duplicate_name_same_user_rejected(authed_client, fake_llm):
    _seed_classify(fake_llm)
    authed_client.post("/api/dishes", json={"name": "X"})
    r = authed_client.post("/api/dishes", json={"name": "X"})
    assert r.status_code == 409


def test_two_users_can_each_have_same_dish_name(authed_client, fake_llm, test_user, test_user_b):
    """Same dish name OK across users; per-user uniqueness."""
    a_token = create_token(user_id=test_user.id, username=test_user.username)
    authed_client.headers.update({"Authorization": f"Bearer {a_token}"})
    _seed_classify(fake_llm)
    r1 = authed_client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r1.status_code == 201

    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    _seed_classify(fake_llm)
    r2 = authed_client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r2.status_code == 201


def test_list_dishes_isolation(authed_client, fake_llm, test_user, test_user_b):
    a_token = create_token(user_id=test_user.id, username=test_user.username)
    authed_client.headers.update({"Authorization": f"Bearer {a_token}"})
    _seed_classify(fake_llm, ingredients=["虾"])
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


def test_edit_dish_updates_fields(authed_client, db_session, test_user):
    d = _make_dish(db_session, test_user.id, name="红烧肉")
    body = {"name": "红烧排骨", "category": "主菜", "cuisine": "苏",
            "main_ingredients": ["排骨", "冰糖"], "spicy": 2, "tags": ["炖"]}
    r = authed_client.put(f"/api/dishes/{d.id}", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["name"] == "红烧排骨"
    assert out["cuisine"] == "苏"
    assert out["main_ingredients"] == ["排骨", "冰糖"]
    assert out["spicy"] == 2
    assert out["needs_review"] is False


def test_edit_dish_updates_suitable_meals(authed_client, db_session, test_user):
    d = _make_dish(db_session, test_user.id, name="粥")
    body = {"name": "白粥", "category": "主菜", "cuisine": "家常",
            "main_ingredients": ["大米"], "spicy": 0, "tags": [],
            "suitable_meals": ["breakfast"]}
    r = authed_client.put(f"/api/dishes/{d.id}", json=body)
    assert r.status_code == 200
    assert r.json()["suitable_meals"] == ["breakfast"]


def test_edit_rename_to_existing_returns_409(authed_client, db_session, test_user):
    _make_dish(db_session, test_user.id, name="番茄炒蛋")
    d2 = _make_dish(db_session, test_user.id, name="红烧肉")
    body = {"name": "番茄炒蛋", "category": None, "cuisine": None,
            "main_ingredients": [], "spicy": 0, "tags": []}
    r = authed_client.put(f"/api/dishes/{d2.id}", json=body)
    assert r.status_code == 409


def test_edit_other_users_dish_returns_404(authed_client, db_session, test_user_b):
    d = _make_dish(db_session, test_user_b.id, name="别人的菜")
    body = {"name": "改名", "category": None, "cuisine": None,
            "main_ingredients": [], "spicy": 0, "tags": []}
    r = authed_client.put(f"/api/dishes/{d.id}", json=body)
    assert r.status_code == 404


def test_edit_requires_auth(client, db_session, test_user):
    d = _make_dish(db_session, test_user.id)
    r = client.put(f"/api/dishes/{d.id}", json={"name": "x", "category": None,
        "cuisine": None, "main_ingredients": [], "spicy": 0, "tags": []})
    assert r.status_code == 401


def test_add_dish_stores_suitable_meals(authed_client, fake_llm):
    fake_llm.classify_queue.append({
        "category": "饮品", "cuisine": "家常", "main_ingredients": ["牛奶"],
        "spicy": 0, "tags": [], "suitable_meals": ["breakfast"],
    })
    r = authed_client.post("/api/dishes", json={"name": "热牛奶"})
    assert r.status_code == 201
    assert r.json()["suitable_meals"] == ["breakfast"]


def test_add_dish_missing_suitable_meals_defaults_all(authed_client, fake_llm):
    fake_llm.classify_queue.append({
        "category": "主菜", "cuisine": "家常", "main_ingredients": ["猪肉"],
        "spicy": 0, "tags": [],
    })
    r = authed_client.post("/api/dishes", json={"name": "回锅肉"})
    assert r.status_code == 201
    assert r.json()["suitable_meals"] == ["breakfast", "lunch", "dinner"]


def test_add_dish_failed_classify_defaults_all_meals(authed_client, fake_llm):
    from app.services.llm.base import LLMParseError
    fake_llm.classify_queue.append(LLMParseError("bad"))
    r = authed_client.post("/api/dishes", json={"name": "神秘菜"})
    assert r.status_code == 201
    body = r.json()
    assert body["needs_review"] is True
    assert body["suitable_meals"] == ["breakfast", "lunch", "dinner"]
