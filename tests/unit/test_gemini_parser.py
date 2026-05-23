import pytest

from app.services.gemini import GeminiParseError, parse_gemini_json


def test_clean_json():
    raw = '{"dishes": [{"name": "x"}]}'
    assert parse_gemini_json(raw) == {"dishes": [{"name": "x"}]}


def test_json_wrapped_in_markdown_fences():
    raw = "```json\n{\"a\": 1}\n```"
    assert parse_gemini_json(raw) == {"a": 1}


def test_json_with_prefix_text():
    raw = "Sure, here you go:\n{\"a\": 1}"
    assert parse_gemini_json(raw) == {"a": 1}


def test_json_with_suffix_text():
    raw = '{"a": 1}\nHope this helps!'
    assert parse_gemini_json(raw) == {"a": 1}


def test_no_braces_raises():
    with pytest.raises(GeminiParseError):
        parse_gemini_json("no json here")


def test_malformed_json_raises():
    with pytest.raises(GeminiParseError):
        parse_gemini_json("{not valid json}")
