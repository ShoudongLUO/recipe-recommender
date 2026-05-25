from __future__ import annotations

from app.services.llm.base import LLMUnavailable

_TIMEOUT = 8.0


class OpenAICompatProvider:
    def __init__(self, api_key: str, base_url: str, model: str, http=None):
        self.model = model
        self.available = bool(api_key and base_url)
        self._key = api_key
        self._base = (base_url or "").rstrip("/")
        if http is not None:
            self._http = http
        else:
            import httpx

            self._http = httpx

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        try:
            r = self._http.post(
                f"{self._base}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(str(e)) from e

    def list_models(self) -> list[str]:
        try:
            r = self._http.get(f"{self._base}/models", headers=self._headers(), timeout=_TIMEOUT)
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(str(e)) from e
