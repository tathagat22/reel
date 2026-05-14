"""Sprint 1.1 — bare proxy + /health smoke."""

from __future__ import annotations

from starlette.testclient import TestClient

from reel import __version__
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app


def test_health_returns_ok_with_metadata() -> None:
    config = ProxyConfig(mode="record", cassette_path="/tmp/x.jsonl")
    app = create_app(config)

    with TestClient(app) as client:
        r = client.get("/health")

    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ok",
        "version": __version__,
        "mode": "record",
        "cassette": "/tmp/x.jsonl",
    }


def test_health_uses_env_defaults_when_no_config_passed() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] in ("record", "replay", "auto")


def test_unknown_path_returns_404_for_now() -> None:
    """Routing arrives in Sprint 1.2. Until then unknown paths are 404."""
    app = create_app(ProxyConfig())
    with TestClient(app) as client:
        r = client.get("/v1/chat/completions")
    assert r.status_code == 404


def test_lifespan_creates_http_client() -> None:
    """The shared httpx client must exist during the lifespan window."""
    app = create_app(ProxyConfig())
    with TestClient(app):
        client = app.state.http_client
        assert client is not None
