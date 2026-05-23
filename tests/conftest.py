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
from app.services.gemini import GeminiClient


class FakeTransport:
    """FIFO queue of scripted responses. Strings are returned, Exceptions are raised."""

    def __init__(self):
        self.responses: list = []
        self.calls: list[tuple[str, float]] = []

    def push(self, response) -> None:
        self.responses.append(response)

    def generate(self, prompt: str, *, temperature: float = 0.7, timeout: float = 8.0) -> str:
        self.calls.append((prompt, temperature))
        if not self.responses:
            raise RuntimeError("FakeTransport: no scripted response")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture()
def fake_transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture()
def fake_gemini(fake_transport) -> GeminiClient:
    return GeminiClient(transport=fake_transport)


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
def client(db_session, fake_gemini) -> Iterator[TestClient]:
    from app.main import app

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    original_gemini = getattr(app.state, "gemini", None)
    app.state.gemini = fake_gemini

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    if original_gemini is not None:
        app.state.gemini = original_gemini


@pytest.fixture()
def authed_client(client, test_user) -> TestClient:
    token = create_token(user_id=test_user.id, username=test_user.username)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
