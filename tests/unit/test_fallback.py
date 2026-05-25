import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LLMConfig, User
from app.services.crypto import encrypt
from app.services.llm.base import LLMUnavailable
from app.services.llm import factory


@pytest.fixture()
def db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, future=True)()
    yield s
    s.close()
    eng.dispose()


def _user(db):
    u = User(id=uuid.uuid4(), username="u", password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_classify_pro_429_falls_back_to_flash(db, monkeypatch):
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="gemini",
            api_key_encrypted=encrypt("k"),
            model="gemini-2.5-pro",
        )
    )
    db.commit()
    calls = {"n": 0}

    def fake_build(db_, user_, *, force_flash=False):
        class S:
            def classify_dish(self, name):
                calls["n"] += 1
                if not force_flash:
                    raise LLMUnavailable("429 RESOURCE_EXHAUSTED")
                return {"category": "主菜", "name": name}

        return S()

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    out = factory.classify_with_fallback(db, u, "番茄炒蛋")
    assert out["category"] == "主菜"
    assert calls["n"] == 2
    assert db.get(LLMConfig, u.id).gemini_fallback_date == date.today()


def test_classify_non_pro_429_no_retry(db, monkeypatch):
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="gemini",
            api_key_encrypted=encrypt("k"),
            model="gemini-2.5-flash",
        )
    )
    db.commit()

    def fake_build(db_, user_, *, force_flash=False):
        class S:
            def classify_dish(self, name):
                raise LLMUnavailable("429 RESOURCE_EXHAUSTED")

        return S()

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    with pytest.raises(LLMUnavailable):
        factory.classify_with_fallback(db, u, "x")


def test_recommend_pro_429_falls_back_and_flags(db, monkeypatch):
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="gemini",
            api_key_encrypted=encrypt("k"),
            model="gemini-2.5-pro",
        )
    )
    db.commit()

    def fake_build(db_, user_, *, force_flash=False):
        class S:
            def generate_new_dishes(self, **kw):
                if not force_flash:
                    raise LLMUnavailable("429 RESOURCE_EXHAUSTED")
                return [{"name": "X"}]

        return S()

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    dishes, fell_back = factory.recommend_new_dishes(
        db,
        u,
        cuisine_prefs=[],
        spicy=0,
        dislikes=[],
        ingredients=[],
        cuisine_histogram={},
        cooked_this_week=[],
    )
    assert dishes == [{"name": "X"}]
    assert fell_back is True
