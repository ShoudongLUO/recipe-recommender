import pytest


def test_get_unconfigured_returns_default(authed_client):
    r = authed_client.get("/api/llm-config")
    assert r.status_code == 200
    b = r.json()
    assert b["using_default"] is True
    assert b["has_key"] is False


def test_put_then_get_masks_key(authed_client):
    r = authed_client.put("/api/llm-config", json={
        "provider": "openai_compat", "api_key": "sk-abcd1234WXYZ",
        "base_url": "https://api.deepseek.com", "model": "deepseek-chat"})
    assert r.status_code == 200
    g = authed_client.get("/api/llm-config").json()
    assert g["provider"] == "openai_compat"
    assert g["model"] == "deepseek-chat"
    assert g["has_key"] is True
    assert g["key_tail"] == "WXYZ"
    assert "api_key" not in g and "api_key_encrypted" not in g
    assert g["using_default"] is False


def test_put_openai_without_base_url_400(authed_client):
    r = authed_client.put("/api/llm-config", json={
        "provider": "openai_compat", "api_key": "k", "base_url": "", "model": "m"})
    assert r.status_code == 400


def test_put_change_model_keeps_key(authed_client):
    authed_client.put("/api/llm-config", json={
        "provider": "gemini", "api_key": "AIza-secret-key1", "model": "gemini-2.5-pro"})
    authed_client.put("/api/llm-config", json={"provider": "gemini", "model": "gemini-2.5-flash"})
    g = authed_client.get("/api/llm-config").json()
    assert g["has_key"] is True
    assert g["model"] == "gemini-2.5-flash"


def test_models_endpoint_ok(authed_client, monkeypatch):
    class FakeProv:
        def list_models(self): return ["m1", "m2"]
    monkeypatch.setattr("app.routes.llm_config._build_probe_provider", lambda provider, api_key, base_url: FakeProv())
    r = authed_client.post("/api/llm-config/models", json={"provider": "gemini", "api_key": "k"})
    assert r.status_code == 200
    assert r.json()["models"] == ["m1", "m2"]


def test_models_endpoint_failure_400(authed_client, monkeypatch):
    from app.services.llm.base import LLMUnavailable
    class FakeProv:
        def list_models(self): raise LLMUnavailable("bad key")
    monkeypatch.setattr("app.routes.llm_config._build_probe_provider", lambda provider, api_key, base_url: FakeProv())
    r = authed_client.post("/api/llm-config/models", json={"provider": "gemini", "api_key": "k"})
    assert r.status_code == 400


def test_config_requires_auth(client):
    assert client.get("/api/llm-config").status_code == 401
