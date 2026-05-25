import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, LLMConfig, User
from app.services.crypto import encrypt
from app.services.llm.base import LLMUnavailable
from app.services.llm.factory import build_llm_for_user, _is_pro, _flash_equiv


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


def test_is_pro_and_flash_equiv():
    assert _is_pro("gemini-2.5-pro") is True
    assert _is_pro("gemini-2.5-flash") is False
    assert _flash_equiv("gemini-2.5-pro") == "gemini-2.5-flash"
    assert _flash_equiv("gemini-1.5-pro") == "gemini-1.5-flash"
    assert _flash_equiv("weird-model") == "gemini-2.5-flash"


def test_unconfigured_uses_env_default(db):
    from app.config import settings

    # If user has no config, should use env defaults
    u = _user(db)
    svc = build_llm_for_user(db, u)
    # Should match the env settings (from .env file)
    assert svc.provider.model == settings.gemini_model
    # If env has gemini_api_key configured, should be available
    if settings.gemini_api_key:
        assert svc.provider.available is True


def test_configured_gemini_uses_config(db):
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="gemini",
            api_key_encrypted=encrypt("mykey"),
            model="gemini-2.5-pro",
        )
    )
    db.commit()
    svc = build_llm_for_user(db, u)
    assert svc.provider.model == "gemini-2.5-pro"


def test_pro_preempt_to_flash_when_fallback_today(db):
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="gemini",
            api_key_encrypted=encrypt("mykey"),
            model="gemini-2.5-pro",
            gemini_fallback_date=date.today(),
        )
    )
    db.commit()
    svc = build_llm_for_user(db, u)
    assert svc.provider.model == "gemini-2.5-flash"


def test_undecryptable_key_does_not_fallback_to_default(db):
    """A stored key that cannot be decrypted (e.g. LLM_ENC_KEY was rotated) must
    NOT silently fall back to the default admin key — it should surface a clear
    decrypt error instead."""
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="gemini",
            api_key_encrypted="this-is-not-a-valid-fernet-token",
            model="gemini-2.5-pro",
        )
    )
    db.commit()
    svc = build_llm_for_user(db, u)
    assert svc.provider.available is False
    with pytest.raises(LLMUnavailable) as e:
        svc.provider.generate("hi")
    assert "decrypt" in str(e.value).lower()


def test_openai_compat_config(db):
    u = _user(db)
    db.add(
        LLMConfig(
            user_id=u.id,
            provider="openai_compat",
            api_key_encrypted=encrypt("k"),
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )
    )
    db.commit()
    svc = build_llm_for_user(db, u)
    assert svc.provider.model == "deepseek-chat"
    assert svc.provider.available is True


def test_plan_new_dishes_falls_back_to_flash_on_quota(monkeypatch, db):
    from app.services.llm import factory

    u = _user(db)
    db.add(LLMConfig(user_id=u.id, provider="gemini",
                     api_key_encrypted=encrypt("k"), model="gemini-2.5-pro"))
    db.commit()

    class _Stub:
        def __init__(self, fail):
            self.fail = fail

        def generate_plan_dishes(self, **kw):
            if self.fail:
                raise LLMUnavailable("429 RESOURCE_EXHAUSTED")
            return [{"name": "X"}]

    def fake_build(db_, user_, *, force_flash=False):
        return _Stub(fail=not force_flash)

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    dishes, fell = factory.plan_new_dishes(
        db, u, cuisine_prefs=[], spicy=2, dislikes=[], known_names=[], count=4)
    assert fell is True
    assert dishes == [{"name": "X"}]


def test_generate_recipe_falls_back_to_flash_on_quota(monkeypatch, db):
    from app.services.llm import factory

    u = _user(db)
    db.add(LLMConfig(user_id=u.id, provider="gemini",
                     api_key_encrypted=encrypt("k"), model="gemini-2.5-pro"))
    db.commit()

    class _Stub:
        def __init__(self, fail):
            self.fail = fail

        def generate_recipe(self, **kw):
            if self.fail:
                raise LLMUnavailable("429 RESOURCE_EXHAUSTED")
            return "做法文本"

    def fake_build(db_, user_, *, force_flash=False):
        return _Stub(fail=not force_flash)

    monkeypatch.setattr(factory, "build_llm_for_user", fake_build)
    text, fell = factory.generate_recipe(
        db, u, name="X", cuisine="家常", main_ingredients=["番茄"])
    assert fell is True
    assert text == "做法文本"
