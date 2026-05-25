import pytest

from app.services.llm.base import parse_llm_json, LLMParseError


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
