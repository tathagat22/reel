"""Sprint 1.3 — OpenAI request fingerprint."""

from __future__ import annotations

import json
from typing import Any

from reel.adapters.openai import fingerprint

CHAT_ENDPOINT = "/v1/chat/completions"


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode()


def test_returns_prefixed_sha256() -> None:
    h = fingerprint(_body({"model": "gpt-5", "messages": []}), endpoint=CHAT_ENDPOINT)
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_identical_bodies_identical_fingerprints() -> None:
    body = _body({"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]})
    assert fingerprint(body, endpoint=CHAT_ENDPOINT) == fingerprint(body, endpoint=CHAT_ENDPOINT)


def test_whitespace_difference_does_not_change_fingerprint() -> None:
    compact = b'{"model":"gpt-5","messages":[{"role":"user","content":"hi"}]}'
    spaced = b'{ "model" : "gpt-5" ,  "messages" : [ { "role" : "user" , "content" : "hi" } ] }'
    assert fingerprint(compact, endpoint=CHAT_ENDPOINT) == fingerprint(
        spaced, endpoint=CHAT_ENDPOINT
    )


def test_key_order_does_not_change_fingerprint() -> None:
    a = _body({"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]})
    b = _body({"messages": [{"content": "hi", "role": "user"}], "model": "gpt-5"})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) == fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_model_change_changes_fingerprint() -> None:
    a = _body({"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]})
    b = _body({"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) != fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_message_content_change_changes_fingerprint() -> None:
    a = _body({"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]})
    b = _body({"model": "gpt-5", "messages": [{"role": "user", "content": "ho"}]})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) != fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_message_order_change_changes_fingerprint() -> None:
    msgs1 = [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]
    msgs2 = [
        {"role": "user", "content": "second"},
        {"role": "user", "content": "first"},
    ]
    a = _body({"model": "gpt-5", "messages": msgs1})
    b = _body({"model": "gpt-5", "messages": msgs2})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) != fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_stream_field_ignored() -> None:
    """Streaming vs non-streaming produce the same content → same fingerprint."""
    a = _body({"model": "gpt-5", "messages": [], "stream": True})
    b = _body({"model": "gpt-5", "messages": [], "stream": False})
    c = _body({"model": "gpt-5", "messages": []})
    h = fingerprint(c, endpoint=CHAT_ENDPOINT)
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) == h
    assert fingerprint(b, endpoint=CHAT_ENDPOINT) == h


def test_user_and_metadata_fields_ignored() -> None:
    base: dict[str, Any] = {"model": "gpt-5", "messages": []}
    a = _body(base)
    b = _body({**base, "user": "alice", "metadata": {"trace": "abc"}})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) == fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_temperature_change_changes_fingerprint() -> None:
    a = _body({"model": "gpt-5", "messages": [], "temperature": 0.7})
    b = _body({"model": "gpt-5", "messages": [], "temperature": 0.2})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) != fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_seed_change_changes_fingerprint() -> None:
    a = _body({"model": "gpt-5", "messages": [], "seed": 1})
    b = _body({"model": "gpt-5", "messages": [], "seed": 2})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) != fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_tool_definitions_change_fingerprint() -> None:
    tools_a: list[Any] = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    tools_b: list[Any] = [{"type": "function", "function": {"name": "browse", "parameters": {}}}]
    a = _body({"model": "gpt-5", "messages": [], "tools": tools_a})
    b = _body({"model": "gpt-5", "messages": [], "tools": tools_b})
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) != fingerprint(b, endpoint=CHAT_ENDPOINT)


def test_endpoint_change_changes_fingerprint() -> None:
    body = _body({"model": "gpt-5", "messages": []})
    a = fingerprint(body, endpoint="/v1/chat/completions")
    b = fingerprint(body, endpoint="/v1/completions")
    assert a != b


def test_empty_body_is_deterministic() -> None:
    assert fingerprint(b"", endpoint=CHAT_ENDPOINT) == fingerprint(b"", endpoint=CHAT_ENDPOINT)


def test_non_json_body_falls_back_to_raw_hash() -> None:
    """Future-proofs the function for multipart/binary endpoints."""
    a = fingerprint(b"not-json-at-all", endpoint="/v1/audio/transcriptions")
    b = fingerprint(b"not-json-at-all", endpoint="/v1/audio/transcriptions")
    c = fingerprint(b"different-bytes", endpoint="/v1/audio/transcriptions")
    assert a == b
    assert a != c


def test_nested_dict_key_order_does_not_matter() -> None:
    a = _body(
        {
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_object", "schema": {"a": 1, "b": 2}},
        }
    )
    b = _body(
        {
            "model": "gpt-5",
            "messages": [{"content": "hi", "role": "user"}],
            "response_format": {"schema": {"b": 2, "a": 1}, "type": "json_object"},
        }
    )
    assert fingerprint(a, endpoint=CHAT_ENDPOINT) == fingerprint(b, endpoint=CHAT_ENDPOINT)
