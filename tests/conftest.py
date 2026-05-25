from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Profile, User
from app.db.session import get_db
from app.services.auth import create_token, hash_password
from app.services.llm import factory as _llm_factory


class FakeLLM:
    """Mock LLM for testing. Queue responses (dicts/lists) or Exceptions."""

    def __init__(self):
        self.classify_queue = []     # dicts or Exceptions
        self.new_dishes_queue = []   # lists or Exceptions
        self.new_calls = 0
        self.plan_queue = []     # lists or Exceptions
        self.plan_calls = 0
        self.recipe_queue = []   # strings or Exceptions
        self.recipe_calls = 0

    def classify(self, name):
        r = self.classify_queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def new_dishes(self):
        self.new_calls += 1
        r = self.new_dishes_queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def plan_dishes(self):
        self.plan_calls += 1
        r = self.plan_queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def recipe(self):
        self.recipe_calls += 1
        r = self.recipe_queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture()
def fake_llm(monkeypatch):
    f = FakeLLM()

    def _classify(db, user, name):
        return f.classify(name)

    def _recommend(db, user, **kwargs):
        return f.new_dishes(), False

    def _plan(db, user, **kwargs):
        return f.plan_dishes(), False

    def _recipe(db, user, **kwargs):
        return f.recipe(), False

    monkeypatch.setattr(_llm_factory, "classify_with_fallback", _classify)
    monkeypatch.setattr(_llm_factory, "recommend_new_dishes", _recommend)
    monkeypatch.setattr(_llm_factory, "plan_new_dishes", _plan)
    monkeypatch.setattr(_llm_factory, "generate_recipe", _recipe)
    return f


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _clear_recommend_cache():
    from app.services.cache import recommend_cache
    recommend_cache._store.clear()
    yield
    recommend_cache._store.clear()


@pytest.fixture()
def test_user(db_session) -> User:
    u = User(
        id=uuid.uuid4(),
        username="alice",
        password_hash=hash_password("pass1234"),
    )
    p = Profile(user_id=u.id, cuisine_prefs=[], spicy=2, dislikes=[])
    db_session.add_all([u, p])
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def test_user_b(db_session) -> User:
    u = User(
        id=uuid.uuid4(),
        username="bob",
        password_hash=hash_password("bobpass12"),
    )
    p = Profile(user_id=u.id, cuisine_prefs=[], spicy=2, dislikes=[])
    db_session.add_all([u, p])
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def client(db_session) -> Iterator[TestClient]:
    from app.main import app

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def authed_client(client, test_user) -> TestClient:
    token = create_token(user_id=test_user.id, username=test_user.username)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
