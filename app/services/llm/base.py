from __future__ import annotations

import json
from typing import Protocol


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


class LLMParseError(LLMError):
    pass


class LLMProvider(Protocol):
    available: bool
    model: str

    def generate(self, prompt: str, *, temperature: float = 0.7) -> str: ...

    def list_models(self) -> list[str]: ...


def parse_llm_json(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise LLMParseError("No JSON object found in response")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMParseError(f"Invalid JSON: {e}") from e
