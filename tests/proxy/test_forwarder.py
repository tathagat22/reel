"""Sprint 1.2 — transparent forwarding via the proxy.

Uses respx to mock the upstream so CI never touches a real LLM API.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"


@pytest.fixture
def app_client() -> TestClient:
    cfg = ProxyConfig(openai_upstream=UPSTREAM)
    return TestClient(create_app(cfg))


def test_unknown_path_returns_clean_404(app_client: TestClient) -> None:
    with app_client as client:
        r = client.get("/totally/unknown/path")
    assert r.status_code == 404
    body = r.json()
    assert body["error"].startswith("reel:")
    assert body["path"] == "/totally/unknown/path"
    assert "hint" in body


@respx.mock
def test_post_chat_completions_forwards_to_upstream(app_client: TestClient) -> None:
    route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"id": "chatcmpl-xyz", "choices": [{"message": {"content": "hi"}}]},
        )
    )

    payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "say hi"}]}
    with app_client as client:
        r = client.post("/v1/chat/completions", json=payload)

    assert route.called
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "hi"

    sent_request = route.calls.last.request
    assert sent_request.method == "POST"
    sent_payload = sent_request.read().decode()
    assert "say hi" in sent_payload


@respx.mock
def test_upstream_4xx_status_propagates(app_client: TestClient) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )
    with app_client as client:
        r = client.post("/v1/chat/completions", json={"model": "gpt-5", "messages": []})
    assert r.status_code == 429
    assert r.json()["error"]["message"] == "rate limited"


@respx.mock
def test_upstream_network_error_returns_502(app_client: TestClient) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )
    with app_client as client:
        r = client.post("/v1/chat/completions", json={"model": "gpt-5"})
    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "reel: upstream request failed"
    assert "boom" in body["detail"]


@respx.mock
def test_query_string_is_forwarded(app_client: TestClient) -> None:
    route = respx.get(f"{UPSTREAM}/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    with app_client as client:
        r = client.get("/v1/models?limit=10")
    assert r.status_code == 200
    assert route.called
    assert route.calls.last.request.url.params["limit"] == "10"


@respx.mock
def test_authorization_forwarded_hop_by_hop_stripped(app_client: TestClient) -> None:
    """`Authorization` must pass through; `Proxy-Authorization` (hop-by-hop) must not.

    Note: `Connection` is intentionally NOT asserted absent — httpx legitimately
    re-adds `Connection: keep-alive` when speaking to the upstream. That's the
    correct hop-by-hop behavior.
    """
    route = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    with app_client as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5"},
            headers={
                "Authorization": "Bearer sk-test",
                "Proxy-Authorization": "Bearer poop",
                "X-Custom-Trace": "trace-123",
            },
        )

    fwd_headers = {k.lower(): v for k, v in route.calls.last.request.headers.items()}
    assert fwd_headers.get("authorization") == "Bearer sk-test"
    assert fwd_headers.get("x-custom-trace") == "trace-123"
    assert "proxy-authorization" not in fwd_headers


def test_health_still_wins_against_catch_all(app_client: TestClient) -> None:
    with app_client as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
