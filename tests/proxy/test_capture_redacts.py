"""Sprint 3.6 + 3.7 — capture-time redaction (record + auto modes)."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from starlette.testclient import TestClient

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"


def _proxy(mode: str, cassette: Path, *, redact_pii: bool = True) -> TestClient:
    cfg = ProxyConfig(
        mode=mode,  # type: ignore[arg-type]
        cassette_path=str(cassette),
        openai_upstream=UPSTREAM,
        redact_pii=redact_pii,
    )
    return TestClient(create_app(cfg))


@respx.mock
def test_recorded_response_secret_is_scrubbed(tmp_path: Path) -> None:
    """If upstream leaks a key (e.g., in error text), the cassette must not."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "your key is sk-AAAAAAAAAAAAAAAAAAAA, sorry"}}]
            },
        )
    )
    cassette_path = tmp_path / "tape.jsonl"
    with _proxy("record", cassette_path) as client:
        r = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "leak?"}]},
        )

    assert r.status_code == 200
    # The client got the original (unredacted) upstream content — only the
    # cassette is scrubbed.
    assert "sk-AAAAAAAAAAAAAAAAAAAA" in r.text

    raw = cassette_path.read_text()
    assert "sk-AAAAAAAAAAAAAAAAAAAA" not in raw
    assert "[redacted:openai-key]" in raw


@respx.mock
def test_recorded_response_email_scrubbed_by_default(tmp_path: Path) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"contact": "reach me at alice@example.com"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    with _proxy("record", cassette_path) as client:
        client.post("/v1/chat/completions", json={"model": "gpt-5", "messages": []})

    raw = cassette_path.read_text()
    assert "alice@example.com" not in raw
    assert "[redacted:email]" in raw


@respx.mock
def test_recorded_response_keeps_email_when_pii_opt_out(tmp_path: Path) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"contact": "alice@example.com"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    with _proxy("record", cassette_path, redact_pii=False) as client:
        client.post("/v1/chat/completions", json={"model": "gpt-5", "messages": []})

    raw = cassette_path.read_text()
    assert "alice@example.com" in raw


@respx.mock
def test_secrets_always_scrubbed_even_with_pii_opt_out(tmp_path: Path) -> None:
    """`redact_pii=False` opts out of PII only — secrets are always scrubbed."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"key": "sk-AAAAAAAAAAAAAAAAAAAA"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    with _proxy("record", cassette_path, redact_pii=False) as client:
        client.post("/v1/chat/completions", json={"model": "gpt-5", "messages": []})

    raw = cassette_path.read_text()
    assert "sk-AAAAAAAAAAAAAAAAAAAA" not in raw


@respx.mock
def test_replay_serves_redacted_content(tmp_path: Path) -> None:
    """After record + replay, the client sees the redacted (cassette-stored) content."""
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"text": "sk-AAAAAAAAAAAAAAAAAAAA"})
    )
    cassette_path = tmp_path / "tape.jsonl"
    payload = {"model": "gpt-5", "messages": []}

    with _proxy("record", cassette_path) as client:
        client.post("/v1/chat/completions", json=payload)

    cassette = Cassette(cassette_path)
    assert cassette.entries()[0].response.body["text"] == "[redacted:openai-key]"

    with _proxy("replay", cassette_path) as client:
        r = client.post("/v1/chat/completions", json=payload)
    assert r.json()["text"] == "[redacted:openai-key]"
