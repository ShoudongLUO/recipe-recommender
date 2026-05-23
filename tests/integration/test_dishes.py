from __future__ import annotations

import json


def test_add_dish_gemini_ok(client, fake_transport):
    fake_transport.push(json.dumps({
        "category": "主菜", "cuisine": "家常",
        "main_ingredients": ["番茄", "鸡蛋"], "spicy": 0, "tags": ["炒"]
    }))
    r = client.post("/api/dishes", json={"name": "番茄炒蛋"})
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "番茄炒蛋"
    assert d["main_ingredients"] == ["番茄", "鸡蛋"]
    assert d["needs_review"] is False
    assert d["source"] == "user_known"


def test_add_dish_gemini_fails_marks_review(client, fake_transport):
    fake_transport.push("garbage output")
    fake_transport.push("more garbage")
    r = client.post("/api/dishes", json={"name": "怪菜"})
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "怪菜"
    assert d["needs_review"] is True
    assert d["main_ingredients"] == []


def test_add_duplicate_name_rejected(client, fake_transport):
    fake_transport.push(json.dumps({
        "category": "主菜", "cuisine": "家常",
        "main_ingredients": ["a"], "spicy": 0, "tags": []
    }))
    client.post("/api/dishes", json={"name": "X"})
    r = client.post("/api/dishes", json={"name": "X"})
    assert r.status_code == 409


def test_list_dishes(client, fake_transport):
    fake_transport.push(json.dumps({
        "category": "主菜", "cuisine": "粤",
        "main_ingredients": ["虾"], "spicy": 0, "tags": []
    }))
    client.post("/api/dishes", json={"name": "白灼虾"})
    r = client.get("/api/dishes")
    assert r.status_code == 200
    names = [d["name"] for d in r.json()]
    assert "白灼虾" in names
