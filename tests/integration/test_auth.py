from __future__ import annotations

from app.db.models import InviteCode


def _seed_invite(db_session, code="GoodInvite01"):
    db_session.add(InviteCode(code=code))
    db_session.commit()


def test_register_success(client, db_session):
    _seed_invite(db_session, "TestCode1234")
    r = client.post("/api/auth/register", json={
        "username": "alice",
        "password": "pass1234",
        "invite_code": "TestCode1234",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "alice"
    assert isinstance(body["token"], str) and len(body["token"]) > 40

    # Invite consumed
    db_session.expire_all()
    inv = db_session.query(InviteCode).filter_by(code="TestCode1234").one()
    assert inv.used_at is not None
    assert inv.used_by_user_id is not None


def test_register_invalid_invite(client, db_session):
    r = client.post("/api/auth/register", json={
        "username": "alice",
        "password": "pass1234",
        "invite_code": "DoesNotExist",
    })
    assert r.status_code == 400


def test_register_used_invite(client, db_session):
    _seed_invite(db_session, "UsedInvite01")
    client.post("/api/auth/register", json={
        "username": "first",
        "password": "pass1234",
        "invite_code": "UsedInvite01",
    })
    r = client.post("/api/auth/register", json={
        "username": "second",
        "password": "pass1234",
        "invite_code": "UsedInvite01",
    })
    assert r.status_code == 400


def test_register_username_taken(client, db_session):
    _seed_invite(db_session, "InviteOne001")
    _seed_invite(db_session, "InviteTwo002")
    client.post("/api/auth/register", json={
        "username": "alice",
        "password": "pass1234",
        "invite_code": "InviteOne001",
    })
    r = client.post("/api/auth/register", json={
        "username": "alice",
        "password": "pass1234",
        "invite_code": "InviteTwo002",
    })
    assert r.status_code == 409


def test_register_bad_username_format(client, db_session):
    _seed_invite(db_session)
    r = client.post("/api/auth/register", json={
        "username": "BadName!",
        "password": "pass1234",
        "invite_code": "GoodInvite01",
    })
    assert r.status_code == 422


def test_register_short_password(client, db_session):
    _seed_invite(db_session)
    r = client.post("/api/auth/register", json={
        "username": "alice",
        "password": "short",
        "invite_code": "GoodInvite01",
    })
    assert r.status_code == 422
