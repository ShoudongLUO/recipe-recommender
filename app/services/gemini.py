from __future__ import annotations

import json


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
