"""Sprint 2.2-2.4 — record mode captures SSE streams with timing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"
CHAT = "/v1/chat/completions"


class _SSEStream(httpx.AsyncByteStream):
    """A minimal async-byte-stream that yields pre-canned chunks with sleeps.

    Used to simulate a real SSE upstream so respx can route to it.
    """

    def __init__(self, chunks: list[bytes], gap_ms: int = 5) -> None:
        self._chunks = chunks
        self._gap_s = gap_ms / 1000

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
            if self._gap_s > 0:
                await asyncio.sleep(self._gap_s)

    async def aclose(self) -> None:
        return None


def _stream_response(chunks: list[bytes], gap_ms: int = 5) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        stream=_SSEStream(chunks, gap_ms=gap_ms),
    )


@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    cfg = ProxyConfig(
        mode="record",
        cassette_path=str(tmp_path / "tape.jsonl"),
        openai_upstream=UPSTREAM,
    )
    return TestClient(create_app(cfg))


@respx.mock
def test_streaming_request_records_chunks_with_timing(
    app_client: TestClient, tmp_path: Path
) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=_stream_response(
            [
                b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
                b"data: [DONE]\n\n",
            ],
            gap_ms=8,
        )
    )

    payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}], "stream": True}
    with app_client as client:
        r = client.post(CHAT, json=payload)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    # The full SSE bytes made it back to the client.
    raw = r.content
    assert b'"Hello"' in raw
    assert b'" world"' in raw
    assert b"[DONE]" in raw

    # Cassette has a streaming entry.
    cassette = Cassette(tmp_path / "tape.jsonl")
    assert len(cassette) == 1
    entry = cassette.entries()[0]
    assert entry.response.body is None
    assert entry.response.stream_chunks is not None
    chunks = entry.response.stream_chunks
    assert len(chunks) == 3
    # Each chunk has a positive timing offset, monotonically increasing.
    offsets = [c.t_offset_ms for c in chunks]
    assert offsets == sorted(offsets)
    # JSON SSE data was parsed for storage (diff-friendly).
    assert chunks[0].data == {"choices": [{"delta": {"content": "Hello"}}]}
    assert chunks[1].data == {"choices": [{"delta": {"content": " world"}}]}
    # The [DONE] sentinel is preserved as a string.
    assert chunks[2].data == "[DONE]"


@respx.mock
def test_non_streaming_request_uses_buffered_path(
    app_client: TestClient, tmp_path: Path
) -> None:
    """A request without stream=true still goes through the buffered codepath."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "buffered"})
    )

    with app_client as client:
        r = client.post(CHAT, json={"model": "gpt-5", "messages": []})

    assert r.status_code == 200
    cassette = Cassette(tmp_path / "tape.jsonl")
    assert len(cassette) == 1
    entry = cassette.entries()[0]
    assert entry.response.stream_chunks is None
    assert entry.response.body == {"id": "buffered"}


@respx.mock
def test_streaming_capture_includes_event_field_when_present(
    app_client: TestClient, tmp_path: Path
) -> None:
    """Anthropic-style streams (event: + data:) preserve the event name."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=_stream_response(
            [
                b'event: message_start\ndata: {"type":"message_start"}\n\n',
                b'event: content_block_delta\ndata: {"delta":"hi"}\n\n',
            ],
            gap_ms=2,
        )
    )

    with app_client as client:
        client.post(
            CHAT,
            json={"model": "gpt-5", "messages": [], "stream": True},
        )

    cassette = Cassette(tmp_path / "tape.jsonl")
    chunks = cassette.entries()[0].response.stream_chunks
    assert chunks is not None
    assert chunks[0].event == "message_start"
    assert chunks[1].event == "content_block_delta"


def test_is_streaming_request_recognizes_flag() -> None:
    from reel.proxy.stream import is_streaming_request

    assert is_streaming_request(b'{"stream": true}') is True
    assert is_streaming_request(b'{"stream": false}') is False
    assert is_streaming_request(b"{}") is False
    assert is_streaming_request(b"") is False
    assert is_streaming_request(b"not json") is False
