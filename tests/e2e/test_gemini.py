"""Sprint 3.3 — Gemini end-to-end record/replay round trip.

Gemini's streaming flag is in the URL verb (``:streamGenerateContent``), not
the body — these tests pin that behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import respx
from starlette.testclient import TestClient

from reel.adapters.gemini import GeminiAdapter
from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

GEMINI = "https://generativelanguage.googleapis.com"
GENERATE = "/v1beta/models/gemini-1.5-pro:generateContent"
STREAM = "/v1beta/models/gemini-1.5-pro:streamGenerateContent"


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


def _proxy(mode: str, cassette: Path) -> TestClient:
    return TestClient(
        create_app(
            ProxyConfig(
                mode=mode,  # type: ignore[arg-type]
                cassette_path=str(cassette),
                gemini_upstream=GEMINI,
                replay_timing_multiplier=0.0,
            )
        )
    )


@respx.mock
def test_gemini_generate_content_buffered(tmp_path: Path) -> None:
    upstream = respx.post(f"{GEMINI}{GENERATE}").mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Hi from Gemini"}],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 4},
            },
        )
    )

    cassette_path = tmp_path / "gemini.jsonl"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
        "generationConfig": {"temperature": 0.7},
    }

    with _proxy("record", cassette_path) as client:
        recorded = client.post(GENERATE, json=payload)
    assert recorded.status_code == 200
    assert recorded.json()["candidates"][0]["content"]["parts"][0]["text"] == "Hi from Gemini"
    assert upstream.call_count == 1

    cassette = Cassette(cassette_path)
    entry = cassette.entries()[0]
    assert entry.provider == "gemini"
    assert entry.response.stream_chunks is None

    with _proxy("replay", cassette_path) as client:
        replayed = client.post(GENERATE, json=payload)
    assert replayed.status_code == 200
    assert replayed.json() == recorded.json()
    assert upstream.call_count == 1


@respx.mock
def test_gemini_stream_generate_content_streaming(tmp_path: Path) -> None:
    """Gemini's stream path is the URL verb — body has no `stream: true` field."""
    upstream = respx.post(f"{GEMINI}{STREAM}").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedSSE(
                [
                    b'data: {"candidates":[{"content":{"parts":[{"text":"Hi"}],"role":"model"}}]}\n\n',
                    b'data: {"candidates":[{"content":{"parts":[{"text":" there"}],"role":"model"}}]}\n\n',
                ],
                gap_ms=2,
            ),
        )
    )

    cassette_path = tmp_path / "gemini-stream.jsonl"
    payload = {"contents": [{"role": "user", "parts": [{"text": "stream"}]}]}

    with _proxy("record", cassette_path) as client:
        recorded = client.post(STREAM, json=payload)
    assert recorded.status_code == 200
    assert b'"Hi"' in recorded.content
    assert b'" there"' in recorded.content
    assert upstream.call_count == 1

    cassette = Cassette(cassette_path)
    entry = cassette.entries()[0]
    assert entry.provider == "gemini"
    assert entry.response.stream_chunks is not None and len(entry.response.stream_chunks) == 2

    with _proxy("replay", cassette_path) as client:
        replayed = client.post(STREAM, json=payload)
    assert replayed.status_code == 200
    assert b'"Hi"' in replayed.content
    assert b'" there"' in replayed.content
    assert upstream.call_count == 1


@respx.mock
def test_gemini_via_explicit_provider_prefix(tmp_path: Path) -> None:
    upstream = respx.post(f"{GEMINI}{GENERATE}").mock(
        return_value=httpx.Response(200, json={"candidates": []})
    )
    cassette_path = tmp_path / "gemini-prefix.jsonl"
    payload = {"contents": []}

    with _proxy("record", cassette_path) as client:
        r = client.post(f"/gemini{GENERATE}", json=payload)

    assert r.status_code == 200
    assert upstream.call_count == 1
    entry = Cassette(cassette_path).entries()[0]
    assert entry.provider == "gemini"
    assert entry.request.path == GENERATE


def test_gemini_adapter_detects_streaming_by_url_verb() -> None:
    a = GeminiAdapter()
    assert a.is_streaming(STREAM, b"") is True
    assert a.is_streaming(GENERATE, b"") is False
    # Even when body says stream:true (irrelevant for Gemini), the URL wins.
    assert a.is_streaming(GENERATE, b'{"stream": true}') is False


def test_gemini_is_in_router_default() -> None:
    from reel.proxy.router import Router

    router = Router.from_config(ProxyConfig())
    providers = {u.provider for u in router.upstreams}
    assert "gemini" in providers
