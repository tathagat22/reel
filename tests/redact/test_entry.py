"""Sprint 3.6 + 3.7 — full CassetteEntry redaction."""

from __future__ import annotations

from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse, StreamChunk
from reel.cassette.writer import generate_id, now_iso
from reel.redact import redact_entry


def _entry_with(response: CassetteResponse) -> CassetteEntry:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(
            method="POST",
            path="/v1/chat/completions",
            fingerprint="sha256:x",
            body={"ok": True},
        ),
        response=response,
    )


def test_redacts_secret_in_response_headers() -> None:
    entry = _entry_with(
        CassetteResponse(
            status=200,
            headers={"x-debug": "leaked Bearer sk-FAKE_FIXTURE_TEST_NOT_REAL"},
            body=None,
        )
    )
    cleaned = redact_entry(entry)
    assert "sk-FAKE_FIXTURE_TEST_NOT_REAL" not in cleaned.response.headers["x-debug"]


def test_redacts_nested_json_body() -> None:
    body = {
        "id": "msg",
        "choices": [
            {"message": {"content": "Your key is sk-FAKE_FIXTURE_TEST_NOT_REAL"}},
        ],
        "metadata": {"contact": "user@example.com"},
    }
    cleaned = redact_entry(_entry_with(CassetteResponse(status=200, headers={}, body=body)))
    serialized = repr(cleaned.response.body)
    assert "sk-FAKE_FIXTURE_TEST_NOT_REAL" not in serialized
    assert "user@example.com" not in serialized
    assert "[redacted:openai-key]" in serialized
    assert "[redacted:email]" in serialized


def test_redacts_stream_chunks() -> None:
    chunks = [
        StreamChunk(data={"delta": {"text": "ping me at alice@example.com"}}, t_offset_ms=0),
        StreamChunk(data="[DONE]", t_offset_ms=10),
    ]
    cleaned = redact_entry(
        _entry_with(
            CassetteResponse(
                status=200, headers={"content-type": "text/event-stream"}, stream_chunks=chunks
            )
        )
    )
    assert cleaned.response.stream_chunks is not None
    serialized = repr(cleaned.response.stream_chunks[0].data)
    assert "alice@example.com" not in serialized
    assert "[redacted:email]" in serialized


def test_scrub_pii_false_keeps_pii_but_still_scrubs_secrets() -> None:
    body = {"text": "ping alice@example.com with key sk-FAKE_FIXTURE_TEST_NOT_REAL"}
    cleaned = redact_entry(
        _entry_with(CassetteResponse(status=200, headers={}, body=body)),
        scrub_pii=False,
    )
    serialized = repr(cleaned.response.body)
    assert "alice@example.com" in serialized
    assert "sk-FAKE_FIXTURE_TEST_NOT_REAL" not in serialized


def test_safe_entry_unchanged() -> None:
    entry = _entry_with(
        CassetteResponse(status=200, headers={}, body={"choices": [{"message": "hi"}]})
    )
    cleaned = redact_entry(entry)
    assert cleaned.response.body == entry.response.body
