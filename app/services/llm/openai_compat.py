from __future__ import annotations

from app.services.llm.base import LLMUnavailable

# Kept under Vercel's serverless function duration limit so a slow upstream
# returns a clean in-app warning rather than a 504. Raising this requires
# raising the function's maxDuration too (see vercel.json / deploy notes).
_TIMEOUT = 8.0


def _describe(e: Exception) -> str:
    """Normalize provider errors so callers can recognize a timeout even when the
    underlying exception (e.g. httpx.ReadTimeout) has an empty str()."""
    if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
        return "request timed out"
    return str(e) or type(e).__name__


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
            raise LLMUnavailable(_describe(e)) from e

    def list_models(self) -> list[str]:
        try:
            r = self._http.get(f"{self._base}/models", headers=self._headers(), timeout=_TIMEOUT)
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(_describe(e)) from e
