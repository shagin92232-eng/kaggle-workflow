"""Unit tests for the LLM client's JSON extraction (no network)."""

import pytest

from agent.llm_client import LLMError, extract_json


def test_plain_json_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_plain_json_array():
    assert extract_json('[{"start": 1.5, "end": 9.0}]') == [{"start": 1.5, "end": 9.0}]


def test_fenced_json():
    text = "Here you go:\n```json\n{\"title\": \"ok\"}\n```\nthanks"
    assert extract_json(text) == {"title": "ok"}


def test_json_with_prose_prefix():
    text = "Sure! The result is [1, 2, 3] as requested."
    assert extract_json(text) == [1, 2, 3]


def test_no_json_raises():
    with pytest.raises(LLMError):
        extract_json("no json here at all")
