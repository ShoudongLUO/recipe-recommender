from __future__ import annotations

from app.services.llm.base import LLMUnavailable


class _RealGeminiTransport:
    def __init__(self, api_key: str, model: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        from google.genai import types

        resp = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return resp.text or ""

    def list_models(self) -> list[str]:
        out = []
        for m in self._client.models.list():
            actions = (
                getattr(m, "supported_actions", None)
                or getattr(m, "supported_generation_methods", None)
                or []
            )
            name = (m.name or "").replace("models/", "")
            if (not actions or "generateContent" in actions) and name:
                out.append(name)
        return out


class GeminiProvider:
    def __init__(self, api_key: str, model: str, transport=None):
        self.model = model
        self.available = bool(api_key)
        self._transport = transport or (
            _RealGeminiTransport(api_key, model) if api_key else None
        )

    def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        if self._transport is None:
            raise LLMUnavailable("no api key")
        try:
            return self._transport.generate(prompt, temperature=temperature)
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(str(e)) from e

    def list_models(self) -> list[str]:
        if self._transport is None:
            raise LLMUnavailable("no api key")
        try:
            return self._transport.list_models()
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(str(e)) from e
