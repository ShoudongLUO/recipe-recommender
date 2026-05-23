import pytest

from app.services.auth import hash_password, verify_password


def test_hash_password_returns_non_empty_string():
    h = hash_password("hello1234")
    assert isinstance(h, str)
    assert len(h) > 20
    assert h != "hello1234"


def test_verify_correct_password():
    h = hash_password("hello1234")
    assert verify_password("hello1234", h) is True


def test_verify_wrong_password():
    h = hash_password("hello1234")
    assert verify_password("wrong1234", h) is False


def test_two_hashes_of_same_password_differ():
    a = hash_password("hello1234")
    b = hash_password("hello1234")
    assert a != b  # salt differs
    assert verify_password("hello1234", a)
    assert verify_password("hello1234", b)


import time
import uuid

from app.services.auth import create_token, decode_token, AuthError


def test_token_roundtrip():
    uid = uuid.uuid4()
    tok = create_token(user_id=uid, username="alice")
    payload = decode_token(tok)
    assert payload["sub"] == str(uid)
    assert payload["username"] == "alice"
    assert "exp" in payload
    assert "iat" in payload


def test_decode_rejects_tampered():
    uid = uuid.uuid4()
    tok = create_token(user_id=uid, username="alice")
    # flip the last two chars (signature region)
    bad = tok[:-2] + ("AA" if tok[-2:] != "AA" else "BB")
    with pytest.raises(AuthError):
        decode_token(bad)


def test_decode_rejects_expired():
    uid = uuid.uuid4()
    tok = create_token(user_id=uid, username="alice", expires_in=-1)
    time.sleep(0.1)
    with pytest.raises(AuthError):
        decode_token(tok)


def test_decode_rejects_garbage():
    with pytest.raises(AuthError):
        decode_token("not-a-jwt")


from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, User
from app.services.auth import current_user


@pytest.fixture()
def fresh_db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, future=True)
    db = S()
    yield db
    db.close()
    eng.dispose()


def _make_user(db, username="alice"):
    u = User(username=username, password_hash=hash_password("pass1234"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_current_user_returns_user(fresh_db):
    u = _make_user(fresh_db)
    tok = create_token(user_id=u.id, username=u.username)
    got = current_user(authorization=f"Bearer {tok}", db=fresh_db)
    assert got.id == u.id


def test_current_user_missing_header(fresh_db):
    with pytest.raises(HTTPException) as e:
        current_user(authorization=None, db=fresh_db)
    assert e.value.status_code == 401


def test_current_user_wrong_scheme(fresh_db):
    with pytest.raises(HTTPException) as e:
        current_user(authorization="Basic abc", db=fresh_db)
    assert e.value.status_code == 401


def test_current_user_bad_token(fresh_db):
    with pytest.raises(HTTPException) as e:
        current_user(authorization="Bearer garbage", db=fresh_db)
    assert e.value.status_code == 401


def test_current_user_user_deleted(fresh_db):
    u = _make_user(fresh_db)
    tok = create_token(user_id=u.id, username=u.username)
    fresh_db.delete(u)
    fresh_db.commit()
    with pytest.raises(HTTPException) as e:
        current_user(authorization=f"Bearer {tok}", db=fresh_db)
    assert e.value.status_code == 401
