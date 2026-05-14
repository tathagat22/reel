"""Sprint 1.6 — record mode integration tests.

Uses respx to mock the OpenAI upstream so CI never touches a real API.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"


@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    cassette_path = tmp_path / "tape.jsonl"
    cfg = ProxyConfig(
        mode="record",
        cassette_path=str(cassette_path),
        openai_upstream=UPSTREAM,
    )
    return TestClient(create_app(cfg))


def test_record_mode_without_cassette_path_returns_400(tmp_path: Path) -> None:
    cfg = ProxyConfig(mode="record", cassette_path=None, openai_upstream=UPSTREAM)
    with TestClient(create_app(cfg)) as client:
        r = client.post("/v1/chat/completions", json={"model": "gpt-5"})
    assert r.status_code == 400
    assert "cassette" in r.json()["error"]


@respx.mock
def test_record_writes_cassette_entry(app_client: TestClient, tmp_path: Path) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"id": "chatcmpl-xyz", "choices": [{"message": {"content": "pong"}}]},
        )
    )

    with app_client as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "ping"}]},
        )

    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "pong"

    cassette_path = tmp_path / "tape.jsonl"
    assert cassette_path.exists()
    lines = cassette_path.read_text().strip().splitlines()
    assert len(lines) == 1

    cassette = Cassette(cassette_path)
    assert len(cassette) == 1
    entry = cassette.entries()[0]
    assert entry.provider == "openai"
    assert entry.request.method == "POST"
    assert entry.request.path == "/v1/chat/completions"
    assert entry.request.fingerprint.startswith("sha256:")
    assert entry.request.body == {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "ping"}],
    }
    assert entry.response.status == 200
    assert entry.response.body == {
        "id": "chatcmpl-xyz",
        "choices": [{"message": {"content": "pong"}}],
    }


@respx.mock
def test_record_does_not_capture_request_headers(app_client: TestClient, tmp_path: Path) -> None:
    """API keys live in headers — cassettes must NEVER include them."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )

    with app_client as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5"},
            headers={"Authorization": "Bearer sk-real-secret"},
        )

    raw = (tmp_path / "tape.jsonl").read_text()
    assert "sk-real-secret" not in raw
    assert "Authorization" not in raw


@respx.mock
def test_record_captures_multiple_requests_in_order(app_client: TestClient, tmp_path: Path) -> None:
    route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json={"choices": [{"message": {"content": "first"}}]}),
            httpx.Response(200, json={"choices": [{"message": {"content": "second"}}]}),
        ]
    )

    with app_client as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "a"}]},
        )
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "b"}]},
        )

    assert route.call_count == 2
    cassette = Cassette(tmp_path / "tape.jsonl")
    assert len(cassette) == 2
    bodies = [e.response.body for e in cassette.entries()]
    assert bodies[0]["choices"][0]["message"]["content"] == "first"
    assert bodies[1]["choices"][0]["message"]["content"] == "second"


@respx.mock
def test_record_persists_upstream_error_status(app_client: TestClient, tmp_path: Path) -> None:
    """A 429 from upstream is a real response — record it faithfully."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )

    with app_client as client:
        r = client.post("/v1/chat/completions", json={"model": "gpt-5"})

    assert r.status_code == 429
    cassette = Cassette(tmp_path / "tape.jsonl")
    assert len(cassette) == 1
    assert cassette.entries()[0].response.status == 429


@respx.mock
def test_record_persists_502_when_upstream_unreachable(
    app_client: TestClient, tmp_path: Path
) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(side_effect=httpx.ConnectError("boom"))

    with app_client as client:
        r = client.post("/v1/chat/completions", json={"model": "gpt-5"})

    assert r.status_code == 502
    # The 502 generated by the forwarder is still recorded.
    cassette = Cassette(tmp_path / "tape.jsonl")
    assert len(cassette) == 1
    assert cassette.entries()[0].response.status == 502
