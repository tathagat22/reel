"""Sprint 3.2 — Anthropic end-to-end record/replay round trip.

Anthropic messages endpoint, both buffered and streaming variants. Tests use
respx-mocked upstream so CI never needs a real API key.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

ANTHROPIC = "https://api.anthropic.com"
MESSAGES = "/v1/messages"


class _CannedSSE(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], gap_ms: int = 2) -> None:
        self._chunks = chunks
        self._gap_s = gap_ms / 1000

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for c in self._chunks:
            yield c
            if self._gap_s > 0:
                await asyncio.sleep(self._gap_s)

    async def aclose(self) -> None:
        return None


def _proxy(mode: str, cassette: Path, timing: float = 0.0) -> TestClient:
    return TestClient(
        create_app(
            ProxyConfig(
                mode=mode,  # type: ignore[arg-type]
                cassette_path=str(cassette),
                anthropic_upstream=ANTHROPIC,
                replay_timing_multiplier=timing,
            )
        )
    )


@respx.mock
def test_anthropic_buffered_round_trip(tmp_path: Path) -> None:
    upstream = respx.post(f"{ANTHROPIC}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_01",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello from Claude."}],
                "model": "claude-opus-4-7",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 7},
            },
        )
    )

    cassette_path = tmp_path / "anthropic.jsonl"
    payload = {
        "model": "claude-opus-4-7",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Hi"}],
    }

    with _proxy("record", cassette_path) as client:
        recorded = client.post(MESSAGES, json=payload)
    assert recorded.status_code == 200
    assert recorded.json()["content"][0]["text"] == "Hello from Claude."
    assert upstream.call_count == 1

    cassette = Cassette(cassette_path)
    assert len(cassette) == 1
    entry = cassette.entries()[0]
    assert entry.provider == "anthropic"
    assert entry.request.body["model"] == "claude-opus-4-7"

    with _proxy("replay", cassette_path) as client:
        replayed = client.post(MESSAGES, json=payload)
    assert replayed.status_code == 200
    assert replayed.json() == recorded.json()
    assert upstream.call_count == 1  # Still 1 — no extra network on replay.


@respx.mock
def test_anthropic_streaming_round_trip(tmp_path: Path) -> None:
    """Anthropic SSE uses both `event:` and `data:` lines per frame."""
    upstream = respx.post(f"{ANTHROPIC}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedSSE(
                [
                    b'event: message_start\ndata: {"type":"message_start","message":{"id":"m1"}}\n\n',
                    b'event: content_block_start\ndata: {"type":"content_block_start","index":0}\n\n',
                    b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"text":"Hi"}}\n\n',
                    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
                    b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
                ],
                gap_ms=2,
            ),
        )
    )

    cassette_path = tmp_path / "anthropic-stream.jsonl"
    payload = {
        "model": "claude-opus-4-7",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "stream please"}],
        "stream": True,
    }

    with _proxy("record", cassette_path) as client:
        recorded = client.post(MESSAGES, json=payload)
    assert recorded.status_code == 200
    assert b"message_start" in recorded.content
    assert b"content_block_delta" in recorded.content
    assert upstream.call_count == 1

    cassette = Cassette(cassette_path)
    entry = cassette.entries()[0]
    assert entry.provider == "anthropic"
    chunks = entry.response.stream_chunks
    assert chunks is not None
    # All five event types were captured.
    events_captured = [c.event for c in chunks]
    assert "message_start" in events_captured
    assert "content_block_delta" in events_captured
    assert "message_stop" in events_captured

    with _proxy("replay", cassette_path) as client:
        replayed = client.post(MESSAGES, json=payload)
    assert replayed.status_code == 200
    assert b"message_start" in replayed.content
    assert b"content_block_delta" in replayed.content
    assert upstream.call_count == 1


@respx.mock
def test_anthropic_via_explicit_provider_prefix(tmp_path: Path) -> None:
    """Multi-provider users hit /anthropic/v1/messages explicitly."""
    upstream = respx.post(f"{ANTHROPIC}/v1/messages").mock(
        return_value=httpx.Response(200, json={"id": "via-prefix", "content": []})
    )
    cassette_path = tmp_path / "anthropic-prefix.jsonl"
    payload = {"model": "claude-opus-4-7", "max_tokens": 10, "messages": []}

    with _proxy("record", cassette_path) as client:
        r = client.post("/anthropic/v1/messages", json=payload)

    assert r.status_code == 200
    assert r.json()["id"] == "via-prefix"
    assert upstream.call_count == 1

    cassette = Cassette(cassette_path)
    entry = cassette.entries()[0]
    assert entry.provider == "anthropic"
    # The stored request path is the upstream-facing one (prefix stripped).
    assert entry.request.path == "/v1/messages"


def test_anthropic_adapter_fingerprint_ignores_stream() -> None:
    """Same content with stream=true and stream=false produce the same Anthropic fingerprint."""
    from reel.adapters.anthropic import fingerprint as anthropic_fp

    a = anthropic_fp(b'{"model":"claude-opus-4-7","messages":[],"stream":true}', endpoint=MESSAGES)
    b = anthropic_fp(b'{"model":"claude-opus-4-7","messages":[],"stream":false}', endpoint=MESSAGES)
    c = anthropic_fp(b'{"model":"claude-opus-4-7","messages":[]}', endpoint=MESSAGES)
    assert a == b == c
