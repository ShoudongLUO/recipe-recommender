from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai import types


class GeminiParseError(ValueError):
    pass


def parse_gemini_json(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise GeminiParseError("No JSON object found in response")
    candidate = raw[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise GeminiParseError(f"Invalid JSON: {e}") from e


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


class GeminiTransport(Protocol):
    def generate(self, prompt: str, *, temperature: float = 0.7, timeout: float = 8.0) -> str: ...


class RealGeminiTransport:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str, *, temperature: float = 0.7, timeout: float = 8.0) -> str:
        resp = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return resp.text or ""


class GeminiUnavailable(RuntimeError):
    pass


class GeminiClient:
    def __init__(self, transport: GeminiTransport | None):
        self._transport = transport

    @property
    def available(self) -> bool:
        return self._transport is not None

    def _call(self, prompt: str, *, temperature: float = 0.7) -> str:
        if self._transport is None:
            raise GeminiUnavailable("GEMINI_API_KEY not configured")
        try:
            return self._transport.generate(prompt, temperature=temperature)
        except Exception as e:
            raise GeminiUnavailable(str(e)) from e

    def classify_dish(self, name: str) -> dict:
        prompt = _load_prompt("classify_dish.txt").format(name=name)
        try:
            raw = self._call(prompt, temperature=0.4)
            return parse_gemini_json(raw)
        except (GeminiUnavailable, GeminiParseError):
            raw = self._call(prompt, temperature=0.6)
            return parse_gemini_json(raw)

    def generate_new_dishes(
        self,
        *,
        cuisine_prefs: list[str],
        spicy: int,
        dislikes: list[str],
        ingredients: list[str],
        cuisine_histogram: dict[str, int],
        cooked_this_week: list[str],
    ) -> list[dict]:
        prompt = _load_prompt("new_dish.txt").format(
            cuisine_prefs=", ".join(cuisine_prefs) or "(无)",
            spicy=spicy,
            dislikes=", ".join(dislikes) or "(无)",
            ingredients=", ".join(ingredients),
            cuisine_histogram=", ".join(f"{k}:{v}" for k, v in cuisine_histogram.items()) or "(空)",
            cooked_this_week=", ".join(cooked_this_week) or "(无)",
        )
        raw = self._call(prompt, temperature=0.7)
        data = parse_gemini_json(raw)
        return list(data.get("dishes", []))


def build_gemini_client() -> GeminiClient:
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key:
        return GeminiClient(transport=None)
    return GeminiClient(transport=RealGeminiTransport(api_key=api_key, model=model))
