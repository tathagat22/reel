"""Sprint 2.7 + 2.8 — streaming E2E + interruption / non-SSE fallback."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"
CHAT = "/v1/chat/completions"


class _CannedSSE(httpx.AsyncByteStream):
    """A canned SSE byte stream with per-chunk sleeps."""

    def __init__(self, chunks: list[bytes], gap_ms: int = 5) -> None:
        self._chunks = chunks
        self._gap_s = gap_ms / 1000

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for c in self._chunks:
            yield c
            if self._gap_s > 0:
                await asyncio.sleep(self._gap_s)

    async def aclose(self) -> None:
        return None


class _ExplodingSSE(httpx.AsyncByteStream):
    """Yields a couple of chunks then raises mid-stream — simulates upstream death."""

    def __init__(self, before_explosion: list[bytes]) -> None:
        self._chunks = before_explosion

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for c in self._chunks:
            yield c
        raise httpx.ReadError("simulated upstream crash mid-stream")

    async def aclose(self) -> None:
        return None


def _proxy(mode: str, cassette: Path, timing: float = 0.0) -> TestClient:
    return TestClient(
        create_app(
            ProxyConfig(
                mode=mode,  # type: ignore[arg-type]
                cassette_path=str(cassette),
                openai_upstream=UPSTREAM,
                replay_timing_multiplier=timing,
            )
        )
    )


# ─── Sprint 2.8: end-to-end round trip ─────────────────────────────────


@respx.mock
def test_streaming_record_then_replay_roundtrip(tmp_path: Path) -> None:
    """Record a streaming chat completion, then replay it — same content, no network."""
    upstream = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedSSE(
                [
                    b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":" there"}}]}\n\n',
                    b"data: [DONE]\n\n",
                ],
                gap_ms=4,
            ),
        )
    )

    cassette_path = tmp_path / "stream.jsonl"
    payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}], "stream": True}

    # ── Record ──
    with _proxy("record", cassette_path) as client:
        recorded = client.post(CHAT, json=payload)

    assert recorded.status_code == 200
    assert b"[DONE]" in recorded.content
    assert upstream.call_count == 1

    cassette = Cassette(cassette_path)
    assert len(cassette) == 1
    captured = cassette.entries()[0].response.stream_chunks
    assert captured is not None and len(captured) == 4

    # ── Replay ──
    with _proxy("replay", cassette_path) as client:
        replayed = client.post(CHAT, json=payload)

    assert replayed.status_code == 200
    # Bytes are content-equivalent (whitespace differs because storage is
    # diff-friendly parsed JSON, not raw bytes) — decode and compare semantics.
    decoded = _decode_sse_data_frames(replayed.content)
    assert {"choices": [{"delta": {"role": "assistant"}}]} in decoded
    assert {"choices": [{"delta": {"content": "Hi"}}]} in decoded
    assert {"choices": [{"delta": {"content": " there"}}]} in decoded
    assert "[DONE]" in decoded
    # No additional upstream calls during replay.
    assert upstream.call_count == 1


@respx.mock
def test_streaming_auto_first_records_second_replays(tmp_path: Path) -> None:
    upstream = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedSSE(
                [b'data: {"chunk":1}\n\n', b'data: {"chunk":2}\n\n', b"data: [DONE]\n\n"],
                gap_ms=1,
            ),
        )
    )
    cassette_path = tmp_path / "auto-stream.jsonl"
    payload = {"model": "gpt-5", "messages": [], "stream": True}

    with _proxy("auto", cassette_path) as client:
        first = client.post(CHAT, json=payload)
    with _proxy("auto", cassette_path) as client:
        second = client.post(CHAT, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert b"[DONE]" in first.content
    assert b"[DONE]" in second.content
    assert upstream.call_count == 1  # Replay used the cassette.


# ─── Sprint 2.7: interruption + non-SSE fallback ───────────────────────


@respx.mock
def test_upstream_crash_mid_stream_does_not_persist_partial(tmp_path: Path) -> None:
    """If upstream dies mid-stream, the cassette stays empty — partial entries would lie."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_ExplodingSSE(
                [
                    b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
                ]
            ),
        )
    )
    cassette_path = tmp_path / "stream.jsonl"
    payload = {"model": "gpt-5", "messages": [], "stream": True}

    with _proxy("record", cassette_path) as client:
        try:
            r = client.post(CHAT, json=payload)
            # Depending on Starlette's behavior, the partial bytes may or may not
            # reach the client — what matters is that the cassette is empty.
            _ = r
        except (httpx.ReadError, RuntimeError, Exception):
            pass

    # No persisted entry — capture.completed never became True.
    assert not cassette_path.exists() or len(Cassette(cassette_path)) == 0


@respx.mock
def test_non_sse_upstream_response_falls_back_to_buffered(tmp_path: Path) -> None:
    """`stream: true` request + JSON error response → buffered cassette entry, not empty stream."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )
    cassette_path = tmp_path / "fallback.jsonl"
    payload = {"model": "gpt-5", "messages": [], "stream": True}

    with _proxy("record", cassette_path) as client:
        r = client.post(CHAT, json=payload)

    assert r.status_code == 429
    assert r.json()["error"]["message"] == "rate limited"

    cassette = Cassette(cassette_path)
    assert len(cassette) == 1
    entry = cassette.entries()[0]
    # Stored as buffered, NOT as a streaming entry with zero chunks.
    assert entry.response.stream_chunks is None
    assert entry.response.body == {"error": {"message": "rate limited"}}
    assert entry.response.status == 429


@respx.mock
def test_fallback_buffered_entry_replays_correctly(tmp_path: Path) -> None:
    """The fallback-buffered entry produced by a 'stream:true → non-SSE' record replays fine."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )
    cassette_path = tmp_path / "fallback.jsonl"
    payload = {"model": "gpt-5", "messages": [], "stream": True}

    with _proxy("record", cassette_path) as client:
        client.post(CHAT, json=payload)

    with _proxy("replay", cassette_path) as client:
        replayed = client.post(CHAT, json=payload)

    assert replayed.status_code == 429
    assert replayed.json()["error"]["message"] == "rate limited"


# ─── Cassette readability ─────────────────────────────────────────────


@respx.mock
def test_recorded_cassette_is_human_readable_json(tmp_path: Path) -> None:
    """Cassette diff should reveal the actual delta strings, not opaque bytes."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedSSE(
                [
                    b'data: {"choices":[{"delta":{"content":"this is human-readable"}}]}\n\n',
                    b"data: [DONE]\n\n",
                ],
                gap_ms=1,
            ),
        )
    )
    cassette_path = tmp_path / "readable.jsonl"
    payload = {"model": "gpt-5", "messages": [], "stream": True}

    with _proxy("record", cassette_path) as client:
        client.post(CHAT, json=payload)

    raw_text = cassette_path.read_text()
    # The delta text is plainly readable in the JSONL (no escape soup).
    assert "this is human-readable" in raw_text


def _decode_sse_data_frames(raw: bytes) -> list[Any]:
    """Strip `data: ` prefix and parse JSON for each SSE frame."""
    frames: list[Any] = []
    for line in raw.decode().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            if payload == "[DONE]":
                frames.append("[DONE]")
            else:
                try:
                    frames.append(json.loads(payload))
                except json.JSONDecodeError:
                    frames.append(payload)
    return frames


@respx.mock
def test_replayed_chunks_decode_to_recorded_payloads(tmp_path: Path) -> None:
    chunks = [
        b'data: {"choices":[{"delta":{"content":"one"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"two"}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedSSE(chunks, gap_ms=1),
        )
    )
    cassette_path = tmp_path / "tape.jsonl"
    payload = {"model": "gpt-5", "messages": [], "stream": True}

    with _proxy("record", cassette_path) as client:
        recorded = client.post(CHAT, json=payload)
    with _proxy("replay", cassette_path) as client:
        replayed = client.post(CHAT, json=payload)

    recorded_payloads = _decode_sse_data_frames(recorded.content)
    replayed_payloads = _decode_sse_data_frames(replayed.content)
    assert recorded_payloads == replayed_payloads
