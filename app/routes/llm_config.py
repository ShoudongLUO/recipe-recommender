from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import LLMConfig, User
from app.db.session import get_db
from app.services.auth import current_user
from app.services.crypto import decrypt, encrypt
from app.services.llm.base import LLMUnavailable
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.openai_compat import OpenAICompatProvider

router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])


class ConfigIn(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ModelsIn(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None


def _build_probe_provider(provider: str, api_key: str, base_url: str | None):
    if provider == "openai_compat":
        return OpenAICompatProvider(api_key, base_url or "", "")
    return GeminiProvider(api_key, settings.gemini_model)


def _serialize(cfg: LLMConfig | None) -> dict:
    if cfg is None or not cfg.api_key_encrypted:
        return {"provider": cfg.provider if cfg else "gemini",
                "base_url": cfg.base_url if cfg else None,
                "model": cfg.model if cfg else None,
                "has_key": False, "key_tail": None, "using_default": True}
    try:
        tail = decrypt(cfg.api_key_encrypted)[-4:]
    except Exception:  # noqa: BLE001
        tail = None
    return {"provider": cfg.provider, "base_url": cfg.base_url, "model": cfg.model,
            "has_key": True, "key_tail": tail, "using_default": False}


@router.get("")
def get_config(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return _serialize(db.get(LLMConfig, user.id))


@router.put("")
def put_config(body: ConfigIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if body.provider not in ("gemini", "openai_compat"):
        raise HTTPException(status_code=422, detail="未知 provider")
    if body.provider == "openai_compat" and not (body.base_url and body.base_url.strip()):
        raise HTTPException(status_code=400, detail="OpenAI 兼容需要服务地址")
    cfg = db.get(LLMConfig, user.id)
    if cfg is None:
        cfg = LLMConfig(user_id=user.id)
        db.add(cfg)
    prev_provider = cfg.provider
    cfg.provider = body.provider
    cfg.base_url = body.base_url
    cfg.model = body.model
    if body.api_key:
        cfg.api_key_encrypted = encrypt(body.api_key)
    if body.api_key or prev_provider != body.provider:
        cfg.gemini_fallback_date = None
    cfg.updated_at = datetime.utcnow()
    db.commit()
    return _serialize(cfg)


@router.post("/models")
def list_models(
    body: ModelsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    api_key = (body.api_key or "").strip()
    base_url = body.base_url
    # No new key supplied -> reuse the user's stored key (so listing models does
    # not force a re-paste unless the user is actually changing the key).
    if not api_key:
        cfg = db.get(LLMConfig, user.id)
        if cfg and cfg.api_key_encrypted:
            try:
                api_key = decrypt(cfg.api_key_encrypted)
            except Exception:  # noqa: BLE001 - bad ciphertext (e.g. LLM_ENC_KEY rotated)
                raise HTTPException(status_code=400, detail="保存的 key 无法读取，请重新输入")
            base_url = base_url or cfg.base_url
    if not api_key:
        raise HTTPException(status_code=400, detail="请先输入 API key")
    try:
        provider = _build_probe_provider(body.provider, api_key, base_url)
        return {"models": provider.list_models()}
    except LLMUnavailable:
        raise HTTPException(status_code=400, detail="无法获取模型，请检查 key 或服务地址")
