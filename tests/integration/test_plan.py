from datetime import date

from app.db.models import ApiQuota, Dish
from app.services.auth import create_token


def _seed_dish(db_session, user_id, **kw) -> Dish:
    d = Dish(
        user_id=user_id, name=kw["name"],
        category=kw.get("category", "主菜"), cuisine=kw.get("cuisine", "家常"),
        main_ingredients=kw.get("main_ingredients", []), spicy=kw.get("spicy", 0),
        tags=[], source=kw.get("source", "user_known"),
        cook_count=kw.get("cook_count", 0), needs_review=False,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def test_plan_candidates_known_sorted_and_dislikes_filtered(authed_client, db_session, fake_llm, test_user):
    authed_client.put("/api/profile", json={"cuisine_prefs": [], "spicy": 2, "dislikes": ["香菜"]})
    _seed_dish(db_session, test_user.id, name="A", cook_count=5)
    _seed_dish(db_session, test_user.id, name="B", cook_count=0)
    _seed_dish(db_session, test_user.id, name="香菜鸡", main_ingredients=["香菜", "鸡肉"])
    fake_llm.plan_queue.append([])
    r = authed_client.post("/api/plan/candidates", json={})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["candidates"]]
    assert "香菜鸡" not in names
    assert names[0] == "A"


def test_plan_candidates_merges_ai_dishes(authed_client, db_session, fake_llm, test_user):
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    fake_llm.plan_queue.append([
        {"name": "罗宋汤", "category": "汤类", "cuisine": "俄式", "spicy": 0,
         "main_ingredients": ["牛肉", "土豆"], "why_recommended": "暖"},
        {"name": "番茄炒蛋", "category": "主菜", "cuisine": "家常", "spicy": 0,
         "main_ingredients": ["番茄", "鸡蛋"], "why_recommended": "dup"},
    ])
    r = authed_client.post("/api/plan/candidates", json={})
    by_name = {c["name"]: c for c in r.json()["candidates"]}
    assert by_name["番茄炒蛋"]["source"] == "known"
    assert by_name["罗宋汤"]["source"] == "ai"
    assert by_name["罗宋汤"]["id"] is None
    assert [c["name"] for c in r.json()["candidates"] if c["source"] == "ai"] == ["罗宋汤"]
    assert r.json()["ai_warning"] is None


def test_plan_candidates_ai_failure_degrades(authed_client, db_session, fake_llm, test_user):
    from app.services.llm.base import LLMUnavailable
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    fake_llm.plan_queue.append(LLMUnavailable("network"))
    r = authed_client.post("/api/plan/candidates", json={})
    body = r.json()
    assert [c["name"] for c in body["candidates"]] == ["番茄炒蛋"]
    assert body["ai_warning"]


def test_plan_candidates_quota_exhausted_skips_ai(authed_client, db_session, fake_llm, test_user):
    _seed_dish(db_session, test_user.id, name="番茄炒蛋", main_ingredients=["番茄", "鸡蛋"])
    db_session.add(ApiQuota(user_id=test_user.id, quota_date=date.today(), count=999))
    db_session.commit()
    r = authed_client.post("/api/plan/candidates", json={})
    body = r.json()
    assert [c["name"] for c in body["candidates"]] == ["番茄炒蛋"]
    assert "配额" in body["ai_warning"]
    assert fake_llm.plan_calls == 0


def test_plan_candidates_isolation(authed_client, db_session, fake_llm, test_user, test_user_b):
    _seed_dish(db_session, test_user.id, name="A's dish", main_ingredients=["番茄"])
    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    fake_llm.plan_queue.append([])
    r = authed_client.post("/api/plan/candidates", json={})
    assert r.json()["candidates"] == []


def test_plan_candidates_requires_auth(client):
    assert client.post("/api/plan/candidates", json={}).status_code == 401
