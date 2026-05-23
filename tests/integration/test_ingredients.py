from __future__ import annotations


def test_get_empty_returns_none(client):
    r = client.get("/api/ingredients")
    assert r.status_code == 200
    assert r.json() == {"week_start": None, "items": []}


def test_put_creates_then_get(client):
    r = client.put("/api/ingredients", json={"items": ["番茄", "鸡蛋", "猪肉"]})
    assert r.status_code == 200
    assert r.json()["items"] == ["番茄", "鸡蛋", "猪肉"]
    assert r.json()["week_start"] is not None

    r2 = client.get("/api/ingredients")
    assert r2.json()["items"] == ["番茄", "鸡蛋", "猪肉"]


def test_put_twice_same_week_overwrites(client):
    client.put("/api/ingredients", json={"items": ["a"]})
    client.put("/api/ingredients", json={"items": ["b", "c"]})
    r = client.get("/api/ingredients")
    assert r.json()["items"] == ["b", "c"]
