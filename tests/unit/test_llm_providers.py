import pytest

from app.services.llm.base import parse_llm_json, LLMParseError, LLMUnavailable
from app.services.llm.gemini_provider import GeminiProvider


def test_parse_clean():
    assert parse_llm_json('{"dishes": []}') == {"dishes": []}


def test_parse_fenced():
    assert parse_llm_json("```json\n{\"a\": 1}\n```") == {"a": 1}


def test_parse_prefix_suffix():
    assert parse_llm_json("ok:\n{\"a\": 1}\nbye") == {"a": 1}


def test_parse_no_json_raises():
    with pytest.raises(LLMParseError):
        parse_llm_json("nope")


def test_parse_bad_json_raises():
    with pytest.raises(LLMParseError):
        parse_llm_json("{bad}")


class _FakeTransport:
    def __init__(self):
        self.responses = []
        self.calls = []

    def push(self, r):
        self.responses.append(r)

    def generate(self, prompt, *, temperature=0.7):
        self.calls.append((prompt, temperature))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def list_models(self):
        return ["gemini-2.5-flash", "gemini-2.5-pro"]


def test_gemini_provider_generate_ok():
    t = _FakeTransport()
    t.push("hello")
    p = GeminiProvider(api_key="x", model="gemini-2.5-flash", transport=t)
    assert p.available is True
    assert p.generate("hi") == "hello"


def test_gemini_provider_generate_wraps_error():
    t = _FakeTransport()
    t.push(RuntimeError("429 RESOURCE_EXHAUSTED"))
    p = GeminiProvider(api_key="x", model="gemini-2.5-pro", transport=t)
    with pytest.raises(LLMUnavailable) as e:
        p.generate("hi")
    assert "429" in str(e.value)


def test_gemini_provider_list_models():
    t = _FakeTransport()
    p = GeminiProvider(api_key="x", model="gemini-2.5-flash", transport=t)
    assert "gemini-2.5-pro" in p.list_models()
