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


from app.services.llm.openai_compat import OpenAICompatProvider


class _FakeHttp:
    def __init__(self):
        self.posts = []
        self.gets = []

    def set_post(self, payload):
        self._post = payload

    def set_get(self, payload):
        self._get = payload

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, json))
        return _Resp(self._post)

    def get(self, url, headers=None, timeout=None):
        self.gets.append(url)
        return _Resp(self._get)


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_openai_generate():
    h = _FakeHttp()
    h.set_post({"choices": [{"message": {"content": "hi there"}}]})
    p = OpenAICompatProvider(api_key="k", base_url="https://api.deepseek.com", model="deepseek-chat", http=h)
    assert p.generate("hello") == "hi there"
    assert h.posts[0][0] == "https://api.deepseek.com/chat/completions"


def test_openai_base_url_trailing_slash_normalized():
    h = _FakeHttp()
    h.set_post({"choices": [{"message": {"content": "x"}}]})
    p = OpenAICompatProvider(api_key="k", base_url="https://api.deepseek.com/", model="m", http=h)
    p.generate("hi")
    assert h.posts[0][0] == "https://api.deepseek.com/chat/completions"


def test_openai_list_models():
    h = _FakeHttp()
    h.set_get({"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]})
    p = OpenAICompatProvider(api_key="k", base_url="https://api.deepseek.com", model="deepseek-chat", http=h)
    assert p.list_models() == ["deepseek-chat", "deepseek-reasoner"]


import json as _json
from app.services.llm.service import LLMService


class _StubProvider:
    available = True
    model = "gemini-2.5-flash"

    def __init__(self, out):
        self._out = out
        self.prompts = []

    def generate(self, prompt, *, temperature=0.7):
        self.prompts.append(prompt)
        return self._out

    def list_models(self):
        return []


def test_service_classify_dish():
    out = _json.dumps(
        {
            "category": "主菜",
            "cuisine": "家常",
            "main_ingredients": ["番茄", "鸡蛋"],
            "spicy": 0,
            "tags": ["炒"],
        }
    )
    svc = LLMService(_StubProvider(out))
    d = svc.classify_dish("番茄炒蛋")
    assert d["cuisine"] == "家常"
    assert d["main_ingredients"] == ["番茄", "鸡蛋"]


def test_service_generate_new_dishes():
    out = _json.dumps({"dishes": [{"name": "X", "main_ingredients": ["番茄"]}]})
    svc = LLMService(_StubProvider(out))
    dishes = svc.generate_new_dishes(
        cuisine_prefs=["川"],
        spicy=2,
        dislikes=[],
        ingredients=["番茄"],
        cuisine_histogram={"川": 1},
        cooked_this_week=[],
    )
    assert dishes[0]["name"] == "X"


def test_generate_new_dishes_includes_meal_label_in_prompt():
    out = _json.dumps({"dishes": []})
    stub = _StubProvider(out)
    svc = LLMService(stub)
    svc.generate_new_dishes(
        cuisine_prefs=[],
        spicy=2,
        dislikes=[],
        ingredients=["鸡蛋"],
        cuisine_histogram={},
        cooked_this_week=[],
        meal_label="早餐",
    )
    assert "早餐" in stub.prompts[0]
    assert "这一餐" in stub.prompts[0]
