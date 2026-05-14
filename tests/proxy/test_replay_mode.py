"""Sprint 1.7 — replay mode integration tests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from reel.adapters.openai import fingerprint as openai_fingerprint
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.writer import CassetteWriter, generate_id, now_iso
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"
CHAT = "/v1/chat/completions"


async def _seed_cassette(
    path: Path,
    *,
    body: Mapping[str, Any],
    response_body: Mapping[str, Any],
    status: int = 200,
) -> str:
    """Pre-populate a cassette with one entry; return the fingerprint we expect."""
    import json

    raw = json.dumps(body).encode()
    fp = openai_fingerprint(raw, endpoint=CHAT)
    writer = CassetteWriter(path)
    await writer.append(
        CassetteEntry(
            id=generate_id(),
            ts=now_iso(),
            provider="openai",
            request=CassetteRequest(method="POST", path=CHAT, fingerprint=fp, body=body),
            response=CassetteResponse(
                status=status,
                headers={"content-type": "application/json"},
                body=response_body,
            ),
        )
    )
    return fp


def _client(tmp_path: Path) -> TestClient:
    cfg = ProxyConfig(
        mode="replay",
        cassette_path=str(tmp_path / "tape.jsonl"),
        openai_upstream=UPSTREAM,
    )
    return TestClient(create_app(cfg))


def test_replay_without_cassette_path_returns_400(tmp_path: Path) -> None:
    cfg = ProxyConfig(mode="replay", cassette_path=None, openai_upstream=UPSTREAM)
    with TestClient(create_app(cfg)) as client:
        r = client.post(CHAT, json={"model": "gpt-5"})
    assert r.status_code == 400
    assert "cassette" in r.json()["error"]


async def test_replay_returns_recorded_response(tmp_path: Path) -> None:
    body = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}
    await _seed_cassette(
        tmp_path / "tape.jsonl",
        body=body,
        response_body={"id": "x", "choices": [{"message": {"content": "stored"}}]},
    )

    with _client(tmp_path) as client:
        r = client.post(CHAT, json=body)

    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "stored"


@respx.mock
async def test_replay_never_touches_network(tmp_path: Path) -> None:
    """If replay ever hits the network, this test will fail noisily."""
    upstream_route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "should not be reached"})
    )

    body = {"model": "gpt-5", "messages": []}
    await _seed_cassette(
        tmp_path / "tape.jsonl",
        body=body,
        response_body={"id": "stored"},
    )

    with _client(tmp_path) as client:
        r = client.post(CHAT, json=body)

    assert r.status_code == 200
    assert r.json()["id"] == "stored"
    assert not upstream_route.called


async def test_replay_404_when_fingerprint_missing(tmp_path: Path) -> None:
    await _seed_cassette(
        tmp_path / "tape.jsonl",
        body={"model": "gpt-5", "messages": [{"role": "user", "content": "recorded"}]},
        response_body={"id": "x"},
    )

    with _client(tmp_path) as client:
        r = client.post(
            CHAT,
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "DIFFERENT"}]},
        )

    assert r.status_code == 404
    body = r.json()
    assert body["error"].startswith("reel:")
    assert body["fingerprint"].startswith("sha256:")
    assert "auto" in body["hint"] or "record" in body["hint"]


async def test_replay_preserves_response_status(tmp_path: Path) -> None:
    """A recorded 429 replays as 429 — we model the recorded API faithfully."""
    body = {"model": "gpt-5", "messages": []}
    await _seed_cassette(
        tmp_path / "tape.jsonl",
        body=body,
        response_body={"error": {"message": "rate limited"}},
        status=429,
    )

    with _client(tmp_path) as client:
        r = client.post(CHAT, json=body)

    assert r.status_code == 429
    assert r.json()["error"]["message"] == "rate limited"


async def test_replay_uses_most_recent_when_duplicate(tmp_path: Path) -> None:
    """Re-recording a request appends a new entry; replay should serve the latest."""
    path = tmp_path / "tape.jsonl"
    body = {"model": "gpt-5", "messages": []}

    await _seed_cassette(path, body=body, response_body={"content": "old"})
    await _seed_cassette(path, body=body, response_body={"content": "new"})

    with _client(tmp_path) as client:
        r = client.post(CHAT, json=body)

    assert r.json()["content"] == "new"


@pytest.mark.asyncio
async def test_replay_ignores_stream_field_in_fingerprint(tmp_path: Path) -> None:
    """A request with stream=true matches a cassette recorded with stream=false."""
    recorded_body = {"model": "gpt-5", "messages": []}
    await _seed_cassette(
        tmp_path / "tape.jsonl",
        body=recorded_body,
        response_body={"content": "ok"},
    )

    with _client(tmp_path) as client:
        r = client.post(CHAT, json={"model": "gpt-5", "messages": [], "stream": True})

    assert r.status_code == 200
    assert r.json()["content"] == "ok"
