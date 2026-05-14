"""Sprint 3.4 — match-mode behavior."""

from __future__ import annotations

import importlib.util
import json

import pytest

from reel.adapters.openai import adapter as openai_adapter
from reel.cassette.matcher import MatchConfig, find
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.writer import generate_id, now_iso

CHAT = "/v1/chat/completions"
FUZZY_AVAILABLE = importlib.util.find_spec("sentence_transformers") is not None


def _entry(body: object, fingerprint: str) -> CassetteEntry:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(method="POST", path=CHAT, fingerprint=fingerprint, body=body),
        response=CassetteResponse(status=200, headers={}, body={"ok": True}),
    )


# ─── normalized (default) ──────────────────────────────────────────────


def test_normalized_matches_via_adapter_fingerprint() -> None:
    body = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}
    raw = json.dumps(body).encode()
    fp = openai_adapter.fingerprint(raw, endpoint=CHAT)

    entries = [_entry(body, fp)]
    result = find(entries, body=raw, path=CHAT, adapter=openai_adapter)
    assert result is not None
    assert result.request.fingerprint == fp


def test_normalized_is_insensitive_to_whitespace_and_key_order() -> None:
    body = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}
    raw = json.dumps(body).encode()
    fp = openai_adapter.fingerprint(raw, endpoint=CHAT)
    entries = [_entry(body, fp)]

    differently_formatted = b'{ "messages":[{"content":"hi","role":"user"}], "model":"gpt-5" }'
    result = find(entries, body=differently_formatted, path=CHAT, adapter=openai_adapter)
    assert result is not None


# ─── exact ─────────────────────────────────────────────────────────────


def test_exact_requires_byte_identical_body() -> None:
    """Round-trip-serialized bodies match in exact mode."""
    parsed_body: object = {"model": "gpt-5", "messages": []}
    # The stored body re-serializes as `json.dumps(parsed_body)` (default spacing).
    canonical = json.dumps(parsed_body).encode()
    fp = openai_adapter.fingerprint(canonical, endpoint=CHAT)
    entries = [_entry(parsed_body, fp)]

    cfg = MatchConfig(mode="exact")
    result = find(entries, body=canonical, path=CHAT, adapter=openai_adapter, config=cfg)
    assert result is not None


def test_exact_rejects_whitespace_difference() -> None:
    """In exact mode, even whitespace differences break the match."""
    compact = b'{"model":"gpt-5","messages":[]}'
    fp = openai_adapter.fingerprint(compact, endpoint=CHAT)
    entries = [_entry(json.loads(compact), fp)]

    cfg = MatchConfig(mode="exact")
    # The stored body re-serializes via json.dumps with default separators,
    # which differs from `compact` (no spaces). So a compact incoming request
    # whose stored form has spaces won't match — exact is strict.
    assert find(entries, body=compact, path=CHAT, adapter=openai_adapter, config=cfg) is None
    # But a body whose serialized form matches the stored one does match.
    re_serialized = json.dumps(json.loads(compact)).encode()
    assert (
        find(entries, body=re_serialized, path=CHAT, adapter=openai_adapter, config=cfg) is not None
    )


def test_exact_rejects_path_mismatch() -> None:
    body = b'{"model":"gpt-5","messages":[]}'
    fp = openai_adapter.fingerprint(body, endpoint=CHAT)
    entries = [_entry(json.loads(body), fp)]

    cfg = MatchConfig(mode="exact")
    result = find(entries, body=body, path="/v1/embeddings", adapter=openai_adapter, config=cfg)
    assert result is None


# ─── ignore-fields ─────────────────────────────────────────────────────


def test_ignore_fields_drops_user_supplied_keys() -> None:
    """A `request_id` that differs per call must not break replay matching."""
    stored = {"model": "gpt-5", "messages": [], "request_id": "abc-123"}
    incoming = b'{"model":"gpt-5","messages":[],"request_id":"xyz-999"}'

    stored_fp = openai_adapter.fingerprint(json.dumps(stored).encode(), endpoint=CHAT)
    entries = [_entry(stored, stored_fp)]

    # Without ignore-fields config, normalized matching fails (request_id differs).
    assert find(entries, body=incoming, path=CHAT, adapter=openai_adapter) is None

    # With ignore-fields config, they match.
    cfg = MatchConfig(mode="ignore-fields", ignore_fields=("request_id",))
    assert find(entries, body=incoming, path=CHAT, adapter=openai_adapter, config=cfg) is not None


def test_ignore_fields_still_respects_adapter_defaults() -> None:
    """Adapter's default ignore (e.g., stream) keeps working in ignore-fields mode."""
    stored = {"model": "gpt-5", "messages": [], "trace": "t1"}
    incoming = b'{"model":"gpt-5","messages":[],"trace":"t2","stream":true}'

    stored_fp = openai_adapter.fingerprint(json.dumps(stored).encode(), endpoint=CHAT)
    entries = [_entry(stored, stored_fp)]
    cfg = MatchConfig(mode="ignore-fields", ignore_fields=("trace",))
    assert find(entries, body=incoming, path=CHAT, adapter=openai_adapter, config=cfg) is not None


# ─── fuzzy ─────────────────────────────────────────────────────────────


def test_fuzzy_raises_helpful_error_when_dep_missing() -> None:
    if FUZZY_AVAILABLE:
        pytest.skip("sentence-transformers is installed — error path not exercised")
    cfg = MatchConfig(mode="fuzzy")
    body = b'{"model":"gpt-5","messages":[{"role":"user","content":"hi"}]}'
    with pytest.raises(RuntimeError, match="reel\\[fuzzy\\]"):
        find([], body=body, path=CHAT, adapter=openai_adapter, config=cfg)


@pytest.mark.skipif(not FUZZY_AVAILABLE, reason="sentence-transformers not installed")
def test_fuzzy_matches_semantically_similar_prompts() -> None:
    stored_body = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
    }
    stored_fp = openai_adapter.fingerprint(json.dumps(stored_body).encode(), endpoint=CHAT)
    entries = [_entry(stored_body, stored_fp)]

    similar = (
        b'{"model":"gpt-5","messages":[{"role":"user","content":"Tell me France\'s capital."}]}'
    )
    cfg = MatchConfig(mode="fuzzy", fuzzy_threshold=0.5)
    result = find(entries, body=similar, path=CHAT, adapter=openai_adapter, config=cfg)
    assert result is not None
