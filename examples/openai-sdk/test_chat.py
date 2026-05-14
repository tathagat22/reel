"""Reel + OpenAI SDK example.

These tests use the canonical ``OPENAI_BASE_URL`` env var that the OpenAI
SDK respects. They run against a respx-mocked upstream (so no API key is
needed) but the integration with the real SDK is identical — point at the
real ``api.openai.com`` and remove the respx setup.
"""

from __future__ import annotations

import os

import httpx
import pytest
import respx

from reel.sdk import cassette

OPENAI_UPSTREAM = "https://api.openai.com"


# Fixture form — cassette path inferred from the test name.
@respx.mock
def test_uses_reel_cassette_fixture(reel_cassette: object) -> None:
    """The reel_cassette fixture spins up a proxy and sets env vars."""
    respx.route(host="127.0.0.1").pass_through()
    respx.post(f"{OPENAI_UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "choices": [
                    {"message": {"role": "assistant", "content": "Hi from fixture."}}
                ],
            },
        )
    )

    # Pretend we're using the OpenAI SDK — for the example, raw httpx suffices.
    base = os.environ["OPENAI_BASE_URL"]
    response = httpx.post(
        f"{base}/chat/completions",
        json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]},
        timeout=5.0,
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hi from fixture."


# Decorator form — explicit path.
@respx.mock
@cassette("examples/openai-sdk/cassettes/explicit.jsonl")
def test_uses_cassette_decorator() -> None:
    respx.route(host="127.0.0.1").pass_through()
    respx.post(f"{OPENAI_UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-2",
                "choices": [
                    {"message": {"role": "assistant", "content": "Hi from decorator."}}
                ],
            },
        )
    )

    base = os.environ["OPENAI_BASE_URL"]
    response = httpx.post(
        f"{base}/chat/completions",
        json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]},
        timeout=5.0,
    )
    assert response.json()["choices"][0]["message"]["content"] == "Hi from decorator."


# Marker form — custom mode.
@pytest.mark.cassette(mode="auto")
@respx.mock
def test_marker_with_auto_mode(reel_cassette: object) -> None:
    respx.route(host="127.0.0.1").pass_through()
    respx.post(f"{OPENAI_UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "chatcmpl-3", "choices": []})
    )

    base = os.environ["OPENAI_BASE_URL"]
    response = httpx.post(
        f"{base}/chat/completions",
        json={"model": "gpt-5", "messages": []},
        timeout=5.0,
    )
    assert response.status_code == 200
