"""Sprint 1.8 — auto mode (replay-if-match, else record)."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"
CHAT = "/v1/chat/completions"


def _client(cassette_path: Path) -> TestClient:
    cfg = ProxyConfig(
        mode="auto",
        cassette_path=str(cassette_path),
        openai_upstream=UPSTREAM,
    )
    return TestClient(create_app(cfg))


def test_auto_without_cassette_returns_400(tmp_path: Path) -> None:
    cfg = ProxyConfig(mode="auto", cassette_path=None, openai_upstream=UPSTREAM)
    with TestClient(create_app(cfg)) as client:
        r = client.post(CHAT, json={"model": "gpt-5"})
    assert r.status_code == 400
    assert "cassette" in r.json()["error"]


@respx.mock
def test_first_call_records_and_returns_upstream(tmp_path: Path) -> None:
    """Cache miss: forward upstream, capture the response into the cassette."""
    upstream_route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"id": "live", "choices": [{"message": {"content": "live"}}]}
        )
    )
    cassette_path = tmp_path / "tape.jsonl"

    with _client(cassette_path) as client:
        r = client.post(
            CHAT, json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}
        )

    assert r.status_code == 200
    assert r.json()["id"] == "live"
    assert upstream_route.call_count == 1
    # Cassette has the entry now.
    cassette = Cassette(cassette_path)
    assert len(cassette) == 1
    assert cassette.entries()[0].response.body["id"] == "live"


@respx.mock
def test_second_identical_call_replays_no_network(tmp_path: Path) -> None:
    """Cache hit: zero network on the second call."""
    upstream_route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"id": "live", "choices": [{"message": {"content": "first"}}]}
        )
    )
    cassette_path = tmp_path / "tape.jsonl"
    payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}

    with _client(cassette_path) as client:
        r1 = client.post(CHAT, json=payload)
        r2 = client.post(CHAT, json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both responses are identical.
    assert r1.json() == r2.json()
    # The upstream was hit ONCE; the second call replayed.
    assert upstream_route.call_count == 1
    # The cassette has exactly one entry.
    assert len(Cassette(cassette_path)) == 1


@respx.mock
def test_different_requests_each_get_recorded(tmp_path: Path) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json={"text": "first"}),
            httpx.Response(200, json={"text": "second"}),
        ]
    )
    cassette_path = tmp_path / "tape.jsonl"

    with _client(cassette_path) as client:
        a = client.post(CHAT, json={"model": "gpt-5", "messages": [{"role": "user", "content": "a"}]})
        b = client.post(CHAT, json={"model": "gpt-5", "messages": [{"role": "user", "content": "b"}]})

    assert a.json()["text"] == "first"
    assert b.json()["text"] == "second"
    assert len(Cassette(cassette_path)) == 2


@respx.mock
def test_auto_survives_cassette_restart(tmp_path: Path) -> None:
    """A fresh proxy instance reads existing cassette and replays without network."""
    upstream_route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "captured"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    payload = {"model": "gpt-5", "messages": []}

    # Session 1: records.
    with _client(cassette_path) as client:
        client.post(CHAT, json=payload)
    assert upstream_route.call_count == 1

    # Session 2: fresh proxy, same cassette, replays without network.
    with _client(cassette_path) as client:
        r = client.post(CHAT, json=payload)
    assert r.json()["id"] == "captured"
    assert upstream_route.call_count == 1  # Still 1 — replay used the cassette.


@respx.mock
def test_streaming_field_ignored_in_match(tmp_path: Path) -> None:
    """Requests differing only by `stream` match the same cassette entry."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"content": "ok"})
    )
    cassette_path = tmp_path / "tape.jsonl"

    with _client(cassette_path) as client:
        # Record with stream=False.
        client.post(CHAT, json={"model": "gpt-5", "messages": [], "stream": False})
        # Replay with stream=True — should hit the cached entry.
        r = client.post(CHAT, json={"model": "gpt-5", "messages": [], "stream": True})

    assert r.json() == {"content": "ok"}
    assert len(Cassette(cassette_path)) == 1
