"""Sprint 2.5-2.6 — streaming replay + timing modes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
import respx
from starlette.testclient import TestClient

from reel.adapters.openai import fingerprint as openai_fingerprint
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse, StreamChunk
from reel.cassette.writer import CassetteWriter, generate_id, now_iso
from reel.cli.main import parse_timing
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"
CHAT = "/v1/chat/completions"


def _client(cassette_path: Path, *, timing_multiplier: float = 1.0) -> TestClient:
    cfg = ProxyConfig(
        mode="replay",
        cassette_path=str(cassette_path),
        openai_upstream=UPSTREAM,
        replay_timing_multiplier=timing_multiplier,
    )
    return TestClient(create_app(cfg))


async def _seed_streaming_cassette(
    path: Path,
    *,
    request_body: dict[str, Any],
    chunks: list[StreamChunk],
    status: int = 200,
) -> str:
    import json

    raw = json.dumps(request_body).encode()
    fp = openai_fingerprint(raw, endpoint=CHAT)
    writer = CassetteWriter(path)
    await writer.append(
        CassetteEntry(
            id=generate_id(),
            ts=now_iso(),
            provider="openai",
            request=CassetteRequest(method="POST", path=CHAT, fingerprint=fp, body=request_body),
            response=CassetteResponse(
                status=status,
                headers={"content-type": "text/event-stream"},
                body=None,
                stream_chunks=chunks,
            ),
        )
    )
    return fp


# ─── Streaming replay basics ───────────────────────────────────────────


async def test_replay_emits_sse_chunks(tmp_path: Path) -> None:
    request_body = {"model": "gpt-5", "messages": [], "stream": True}
    chunks = [
        StreamChunk(data={"delta": "Hello"}, t_offset_ms=0),
        StreamChunk(data={"delta": " world"}, t_offset_ms=10),
        StreamChunk(data="[DONE]", t_offset_ms=15),
    ]
    await _seed_streaming_cassette(
        tmp_path / "tape.jsonl", request_body=request_body, chunks=chunks
    )

    with _client(tmp_path / "tape.jsonl", timing_multiplier=0.0) as client:
        r = client.post(CHAT, json=request_body)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.content.decode()

    # Each chunk reconstructed as `data: ...\n\n`.
    assert 'data: {"delta": "Hello"}' in body
    assert 'data: {"delta": " world"}' in body
    assert "data: [DONE]" in body
    # Frames separated by blank lines.
    assert body.count("\n\n") >= 3


async def test_replay_fast_mode_has_no_sleeps(tmp_path: Path) -> None:
    """With multiplier=0 a long captured stream still replays instantly."""
    chunks = [StreamChunk(data={"i": i}, t_offset_ms=i * 200) for i in range(20)]
    body = {"model": "gpt-5", "messages": [], "stream": True}
    await _seed_streaming_cassette(tmp_path / "tape.jsonl", request_body=body, chunks=chunks)

    start = time.monotonic()
    with _client(tmp_path / "tape.jsonl", timing_multiplier=0.0) as client:
        r = client.post(CHAT, json=body)
    elapsed = time.monotonic() - start

    assert r.status_code == 200
    # Captured offsets totaled 3800 ms; fast replay should be << 1 s.
    assert elapsed < 1.0, f"fast replay took {elapsed:.3f}s — should be near zero"


async def test_replay_realtime_mode_preserves_inter_chunk_gap(tmp_path: Path) -> None:
    """With multiplier=1.0 the sum of gaps is preserved within a small margin."""
    chunks = [
        StreamChunk(data={"i": 0}, t_offset_ms=0),
        StreamChunk(data={"i": 1}, t_offset_ms=80),
        StreamChunk(data={"i": 2}, t_offset_ms=160),
    ]
    body = {"model": "gpt-5", "messages": [], "stream": True}
    await _seed_streaming_cassette(tmp_path / "tape.jsonl", request_body=body, chunks=chunks)

    start = time.monotonic()
    with _client(tmp_path / "tape.jsonl", timing_multiplier=1.0) as client:
        r = client.post(CHAT, json=body)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert r.status_code == 200
    # Expect ~160ms. Allow generous margin for test scheduling jitter.
    assert 100 <= elapsed_ms < 1000, f"realtime replay took {elapsed_ms:.0f}ms"


async def test_replay_preserves_event_field(tmp_path: Path) -> None:
    chunks = [
        StreamChunk(data={"t": "start"}, t_offset_ms=0, event="message_start"),
        StreamChunk(data={"d": "hi"}, t_offset_ms=10, event="content_block_delta"),
    ]
    body = {"model": "gpt-5", "messages": [], "stream": True}
    await _seed_streaming_cassette(tmp_path / "tape.jsonl", request_body=body, chunks=chunks)

    with _client(tmp_path / "tape.jsonl", timing_multiplier=0.0) as client:
        r = client.post(CHAT, json=body)

    text = r.content.decode()
    assert "event: message_start" in text
    assert "event: content_block_delta" in text


async def test_replay_404_for_missing_streaming_request(tmp_path: Path) -> None:
    """A stream=true request with no matching cassette entry → 404."""
    body = {"model": "gpt-5", "messages": [], "stream": True}
    # Empty cassette
    (tmp_path / "tape.jsonl").write_text("")
    with _client(tmp_path / "tape.jsonl") as client:
        r = client.post(CHAT, json=body)
    assert r.status_code == 404


@respx.mock
async def test_replay_streaming_does_not_touch_network(tmp_path: Path) -> None:
    upstream_route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"err": "should not be reached"})
    )
    chunks = [StreamChunk(data={"x": 1}, t_offset_ms=0)]
    body = {"model": "gpt-5", "messages": [], "stream": True}
    await _seed_streaming_cassette(tmp_path / "tape.jsonl", request_body=body, chunks=chunks)

    with _client(tmp_path / "tape.jsonl", timing_multiplier=0.0) as client:
        r = client.post(CHAT, json=body)

    assert r.status_code == 200
    assert not upstream_route.called


# ─── Timing parsing ────────────────────────────────────────────────────


def testparse_timing_realtime() -> None:
    assert parse_timing("realtime") == 1.0


def testparse_timing_fast() -> None:
    assert parse_timing("fast") == 0.0


def testparse_timing_slow_n() -> None:
    assert parse_timing("slow=2") == 2.0
    assert parse_timing("slow=0.5") == 0.5


def testparse_timing_bare_number() -> None:
    assert parse_timing("1.5") == 1.5
    assert parse_timing("0.25") == 0.25


def testparse_timing_rejects_garbage() -> None:
    import pytest
    import typer

    with pytest.raises(typer.BadParameter):
        parse_timing("nope")
    with pytest.raises(typer.BadParameter):
        parse_timing("slow=zero")
    with pytest.raises(typer.BadParameter):
        parse_timing("slow=0")
    with pytest.raises(typer.BadParameter):
        parse_timing("slow=-1")
