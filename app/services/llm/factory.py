from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import LLMConfig, User
from app.services.crypto import decrypt
from app.services.llm.base import LLMUnavailable
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.openai_compat import OpenAICompatProvider
from app.services.llm.service import LLMService


def _is_pro(model: str | None) -> bool:
    return bool(model) and "pro" in model.lower()


def _flash_equiv(model: str | None) -> str:
    if model and "pro" in model.lower():
        return model.lower().replace("pro", "flash")
    return "gemini-2.5-flash"


class _UnavailableProvider:
    available = False
    model = ""

    def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        raise LLMUnavailable("no LLM configured")

    def list_models(self) -> list[str]:
        raise LLMUnavailable("no LLM configured")


def _build_provider(cfg: LLMConfig | None, *, force_flash: bool = False):
    if cfg and cfg.api_key_encrypted:
        try:
            key = decrypt(cfg.api_key_encrypted)
        except Exception:  # noqa: BLE001 - bad ciphertext -> treat as unconfigured
            key = None
        if key:
            if cfg.provider == "openai_compat":
                return OpenAICompatProvider(key, cfg.base_url or "", cfg.model or "")
            model = cfg.model or settings.gemini_model
            if force_flash or (_is_pro(model) and cfg.gemini_fallback_date == date.today()):
                model = _flash_equiv(model)
            return GeminiProvider(key, model)
    if settings.gemini_api_key:
        model = settings.gemini_model
        if force_flash:
            model = _flash_equiv(model)
        return GeminiProvider(settings.gemini_api_key, model)
    return _UnavailableProvider()


def build_llm_for_user(
    db: Session, user: User, *, force_flash: bool = False
) -> LLMService:
    cfg = db.get(LLMConfig, user.id)
    return LLMService(_build_provider(cfg, force_flash=force_flash))


def is_gemini_pro_config(db: Session, user: User) -> bool:
    cfg = db.get(LLMConfig, user.id)
    if cfg and cfg.api_key_encrypted:
        return cfg.provider == "gemini" and _is_pro(cfg.model or settings.gemini_model)
    return bool(settings.gemini_api_key) and _is_pro(settings.gemini_model)


def mark_pro_exhausted(db: Session, user: User) -> None:
    cfg = db.get(LLMConfig, user.id)
    if cfg is None:
        cfg = LLMConfig(user_id=user.id, provider="gemini")
        db.add(cfg)
    cfg.gemini_fallback_date = date.today()
    db.commit()
