from app.services.auth import create_token


def test_get_default_profile(authed_client):
    r = authed_client.get("/api/profile")
    assert r.status_code == 200
    assert r.json() == {"cuisine_prefs": [], "spicy": 2, "dislikes": []}


def test_put_profile_updates(authed_client):
    body = {"cuisine_prefs": ["川", "粤"], "spicy": 4, "dislikes": ["香菜"]}
    r = authed_client.put("/api/profile", json=body)
    assert r.status_code == 200
    assert r.json() == body
    r2 = authed_client.get("/api/profile")
    assert r2.json() == body


def test_profile_isolation(authed_client, test_user, test_user_b):
    """Updating user A's profile must not affect user B's."""
    a_token = create_token(user_id=test_user.id, username=test_user.username)
    authed_client.headers.update({"Authorization": f"Bearer {a_token}"})
    authed_client.put("/api/profile", json={
        "cuisine_prefs": ["川"], "spicy": 5, "dislikes": []
    })

    b_token = create_token(user_id=test_user_b.id, username=test_user_b.username)
    authed_client.headers.update({"Authorization": f"Bearer {b_token}"})
    r = authed_client.get("/api/profile")
    assert r.json() == {"cuisine_prefs": [], "spicy": 2, "dislikes": []}


def test_no_auth_returns_401(client):
    r = client.get("/api/profile")
    assert r.status_code == 401
