"""Sprint 1.6 — body codec round-trip."""

from __future__ import annotations

from reel.cassette.body import RAW_KEY, parse_for_storage, serialize_from_storage


def test_empty_body_round_trip() -> None:
    assert parse_for_storage(b"") is None
    assert serialize_from_storage(None) == b""


def test_json_object_round_trip() -> None:
    body = b'{"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}'
    parsed = parse_for_storage(body)
    assert parsed == {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}

    re_serialized = serialize_from_storage(parsed)
    # Bytes may not be byte-identical (whitespace) but the parsed form is.
    import json

    assert json.loads(re_serialized) == json.loads(body)


def test_non_json_body_is_base64_envelope() -> None:
    raw = b"\x00\x01\x02not-json"
    parsed = parse_for_storage(raw)
    assert isinstance(parsed, dict)
    assert RAW_KEY in parsed

    assert serialize_from_storage(parsed) == raw


def test_string_body_round_trip() -> None:
    assert serialize_from_storage("hello") == b"hello"


def test_list_body_round_trip() -> None:
    parsed = parse_for_storage(b"[1,2,3]")
    assert parsed == [1, 2, 3]
    assert serialize_from_storage(parsed) == b"[1, 2, 3]"


def test_invalid_envelope_value_raises() -> None:
    import pytest

    with pytest.raises(TypeError):
        serialize_from_storage({RAW_KEY: 123})
