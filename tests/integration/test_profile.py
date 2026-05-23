from __future__ import annotations


def test_get_default_profile(client):
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json() == {"cuisine_prefs": [], "spicy": 2, "dislikes": []}


def test_put_profile_updates(client):
    body = {"cuisine_prefs": ["川", "粤"], "spicy": 4, "dislikes": ["香菜"]}
    r = client.put("/api/profile", json=body)
    assert r.status_code == 200
    assert r.json() == body
    r2 = client.get("/api/profile")
    assert r2.json() == body
