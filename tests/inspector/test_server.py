"""Sprint 6.1-6.3 — web inspector server.

Uses ``starlette.testclient.TestClient`` which drives the ASGI lifespan
end-to-end, so the cassette is loaded by ``_lifespan`` exactly as it would
be under uvicorn. Filter semantics are exercised via query strings on the
HTMX endpoint ``/entries`` — those mirror what the form submits.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from reel.cassette.schema import (
    CassetteEntry,
    CassetteRequest,
    CassetteResponse,
    StreamChunk,
)
from reel.cassette.writer import generate_id, now_iso
from reel.inspector.server import create_app


def _entry(
    *,
    provider: str = "openai",
    path: str = "/v1/chat/completions",
    model: str | None = "gpt-5",
    status: int = 200,
    request_body: dict[str, object] | None = None,
    response_body: dict[str, object] | None = None,
    stream_chunks: list[StreamChunk] | None = None,
) -> CassetteEntry:
    body: dict[str, object] = request_body or {"messages": []}
    if model is not None:
        body = {"model": model, **body}
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(method="POST", path=path, fingerprint="sha256:x", body=body),
        response=CassetteResponse(
            status=status,
            headers={},
            body=response_body if stream_chunks is None else None,
            stream_chunks=stream_chunks,
        ),
    )


def _write_cassette(path: Path, entries: list[CassetteEntry]) -> None:
    path.write_text(
        "\n".join(e.model_dump_json() for e in entries) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def cassette_path(tmp_path: Path) -> Path:
    path = tmp_path / "tape.jsonl"
    _write_cassette(
        path,
        [
            _entry(
                provider="openai",
                model="gpt-5",
                status=200,
                response_body={"text": "hello-needle"},
            ),
            _entry(
                provider="anthropic",
                model="claude-opus-4-7",
                status=429,
                response_body={"text": "rate-limited"},
            ),
            _entry(
                provider="openai",
                model="gpt-4o",
                status=200,
                request_body={"messages": [], "tools": [{"name": "search"}]},
                response_body={"text": "tooling"},
            ),
        ],
    )
    return path


@pytest.fixture
def client(cassette_path: Path) -> TestClient:
    app = create_app(cassette_path)
    return TestClient(app)


# ─── Smoke tests for each route ────────────────────────────────────────


def test_index_renders_filter_form(client: TestClient, cassette_path: Path) -> None:
    """GET / returns 200 and includes the filter form + the cassette path banner."""
    with client:
        response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert 'hx-get="/entries"' in body
    assert str(cassette_path) in body
    assert "provider" in body
    assert "regex" in body


def test_entries_provider_filter(client: TestClient) -> None:
    """Provider filter narrows rows to a single openai vs anthropic family."""
    with client:
        response = client.get("/entries", params={"provider": "openai"})
    assert response.status_code == 200
    body = response.text
    assert "gpt-5" in body
    assert "gpt-4o" in body
    assert "claude-opus-4-7" not in body
    assert "2 of 3" in body  # match-count footer


def test_entries_status_class_filter(client: TestClient) -> None:
    """``status=4xx`` keeps only the 429 anthropic row."""
    with client:
        response = client.get("/entries", params={"status": "4xx"})
    assert response.status_code == 200
    body = response.text
    assert "429" in body
    assert "claude-opus-4-7" in body
    assert "gpt-5" not in body


def test_entries_regex_searches_body(client: TestClient) -> None:
    """Regex is applied to the JSON-serialized entry — body content matches."""
    with client:
        response = client.get("/entries", params={"regex": "needle"})
    assert response.status_code == 200
    body = response.text
    assert "1 of 3" in body
    assert "gpt-5" in body
    assert "claude-opus-4-7" not in body


def test_entries_has_tool_call_filter(client: TestClient) -> None:
    """Only the gpt-4o entry declares a tool — the filter must isolate it."""
    with client:
        response = client.get("/entries", params={"has_tool_call": "true"})
    assert response.status_code == 200
    body = response.text
    assert "gpt-4o" in body
    assert "gpt-5" not in body
    assert "claude-opus-4-7" not in body


def test_entry_detail_renders_request_and_response(client: TestClient) -> None:
    """Detail page shows the request + response bodies in pretty JSON."""
    with client:
        response = client.get("/entries/0")
    assert response.status_code == 200
    body = response.text
    # request body shows up...
    assert "gpt-5" in body
    # ...alongside the response payload
    assert "hello-needle" in body
    # ...and the breadcrumb link back to the index
    assert 'href="/"' in body


def test_entry_detail_out_of_range_404s(client: TestClient) -> None:
    """A non-existent entry index yields a clean 404 instead of a 500."""
    with client:
        response = client.get("/entries/9999")
    assert response.status_code == 404


def test_create_app_raises_for_missing_cassette(tmp_path: Path) -> None:
    """Missing cassette path is reported at app-build time — uvicorn never binds."""
    with pytest.raises(FileNotFoundError):
        create_app(tmp_path / "does-not-exist.jsonl")
