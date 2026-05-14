"""Sprint 1.10 — E2E record→replay round trip through the real proxy.

These tests prove the *user-visible* contract: record a session against a
mocked upstream, then start a second proxy in replay mode against the same
cassette and assert byte-identical responses with zero new network traffic.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"


def _proxy(mode: str, cassette: Path) -> TestClient:
    return TestClient(
        create_app(
            ProxyConfig(
                mode=mode,  # type: ignore[arg-type]
                cassette_path=str(cassette),
                openai_upstream=UPSTREAM,
            )
        )
    )


@respx.mock
def test_chat_completions_record_then_replay(tmp_path: Path) -> None:
    upstream = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-real",
                "object": "chat.completion",
                "model": "gpt-5",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hi from upstream."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            },
        )
    )

    cassette_path = tmp_path / "chat.jsonl"
    payload = {
        "model": "gpt-5",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say hi"},
        ],
        "temperature": 0.7,
    }

    # ── Phase 1: record ──
    with _proxy("record", cassette_path) as client:
        recorded = client.post("/v1/chat/completions", json=payload)

    assert recorded.status_code == 200
    body = recorded.json()
    assert body["choices"][0]["message"]["content"] == "Hi from upstream."
    assert upstream.call_count == 1
    assert len(Cassette(cassette_path)) == 1

    # ── Phase 2: replay ──
    with _proxy("replay", cassette_path) as client:
        replayed = client.post("/v1/chat/completions", json=payload)

    assert replayed.status_code == 200
    assert replayed.json() == body
    # Upstream NEVER hit again.
    assert upstream.call_count == 1


@respx.mock
def test_embeddings_round_trip(tmp_path: Path) -> None:
    upstream = respx.post(f"{UPSTREAM}/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
                "model": "text-embedding-3-small",
            },
        )
    )

    cassette_path = tmp_path / "embed.jsonl"
    payload = {"model": "text-embedding-3-small", "input": "hello world"}

    with _proxy("record", cassette_path) as client:
        a = client.post("/v1/embeddings", json=payload)
    with _proxy("replay", cassette_path) as client:
        b = client.post("/v1/embeddings", json=payload)

    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert a.json()["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    assert upstream.call_count == 1


@respx.mock
def test_tool_call_round_trip(tmp_path: Path) -> None:
    """Chat completions with tools (function calls) survive the round trip."""
    upstream = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-toolcall",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_001",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city": "Boston"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
        )
    )

    cassette_path = tmp_path / "tool.jsonl"
    payload = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "Weather in Boston?"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
    }

    with _proxy("auto", cassette_path) as client:
        a = client.post("/v1/chat/completions", json=payload)
    with _proxy("replay", cassette_path) as client:
        b = client.post("/v1/chat/completions", json=payload)

    assert a.status_code == 200
    assert b.json() == a.json()
    # tool_calls field survives intact.
    assert b.json()["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert upstream.call_count == 1


@respx.mock
def test_auto_mode_full_user_journey(tmp_path: Path) -> None:
    """The recommended dev workflow: every test run uses `auto`; first run records,
    subsequent runs replay. This test simulates two sequential runs."""
    upstream = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "captured", "content": "ok"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}

    # First run — records.
    with _proxy("auto", cassette_path) as client:
        first = client.post("/v1/chat/completions", json=payload)
    # Second run — replays without touching upstream.
    with _proxy("auto", cassette_path) as client:
        second = client.post("/v1/chat/completions", json=payload)

    assert first.json() == second.json()
    assert upstream.call_count == 1, "Auto mode hit the upstream more than once"


@respx.mock
def test_replay_404_when_cassette_missing_a_request(tmp_path: Path) -> None:
    """Replay refuses to silently fall through to upstream — even though the upstream
    is reachable."""
    upstream_calls = respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"should": "never appear"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    # Cassette is created but empty.
    cassette_path.write_text("")

    with _proxy("replay", cassette_path) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "x"}]},
        )

    assert r.status_code == 404
    assert "no cassette entry" in r.json()["error"]
    assert upstream_calls.called is False
