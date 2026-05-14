"""Sprint 4.1 — @cassette decorator lifecycle, env override, async support.

These tests start a *real* uvicorn server per @cassette context, so they're
the slowest in the suite (~100ms each). Worth it — anything less doesn't
prove the decorator works against real clients.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
import respx

from reel.cassette.store import Cassette
from reel.sdk import cassette, proxy_context

# ─── Lifecycle ─────────────────────────────────────────────────────────


def test_env_var_set_inside_set_unset_outside(tmp_path: Path) -> None:
    """OPENAI_BASE_URL must be present during the test and gone after."""
    before = os.environ.get("OPENAI_BASE_URL")

    inside_url: str | None = None

    @cassette(tmp_path / "tape.jsonl")
    def the_test() -> None:
        nonlocal inside_url
        inside_url = os.environ.get("OPENAI_BASE_URL")

    the_test()

    assert inside_url is not None
    assert inside_url.startswith("http://127.0.0.1:")
    assert inside_url.endswith("/v1")
    assert os.environ.get("OPENAI_BASE_URL") == before  # restored


def test_existing_env_is_restored(tmp_path: Path) -> None:
    """A pre-existing OPENAI_BASE_URL is restored to its original value."""
    os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"

    @cassette(tmp_path / "tape.jsonl")
    def the_test() -> None:
        # Inside, env is shadowed.
        assert os.environ["OPENAI_BASE_URL"].startswith("http://127.0.0.1:")

    try:
        the_test()
        assert os.environ["OPENAI_BASE_URL"] == "https://api.openai.com/v1"
    finally:
        del os.environ["OPENAI_BASE_URL"]


def test_proxy_is_reachable_inside_decorator(tmp_path: Path) -> None:
    """`/health` responds 200 while the decorated function runs."""
    health_status: int | None = None

    @cassette(tmp_path / "tape.jsonl")
    def the_test() -> None:
        nonlocal health_status
        base = os.environ["OPENAI_BASE_URL"].removesuffix("/v1")
        r = httpx.get(f"{base}/health", timeout=2.0)
        health_status = r.status_code

    the_test()
    assert health_status == 200


# ─── Async ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_decorator(tmp_path: Path) -> None:
    inside_url: str | None = None

    @cassette(tmp_path / "tape.jsonl")
    async def the_test() -> None:
        nonlocal inside_url
        inside_url = os.environ.get("OPENAI_BASE_URL")

    await the_test()
    assert inside_url is not None
    assert inside_url.startswith("http://127.0.0.1:")


# ─── End-to-end with mocked upstream ──────────────────────────────────


@respx.mock
def test_record_then_replay_via_decorator(tmp_path: Path) -> None:
    """A full record→replay round trip through the decorator."""
    # Let real localhost calls (to our spawned proxy) pass through; only
    # mock the upstream api.openai.com call.
    respx.route(host="127.0.0.1").pass_through()
    upstream = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "x", "content": "first run"})
    )

    cassette_path = tmp_path / "tape.jsonl"

    @cassette(cassette_path)
    def the_test() -> dict[str, object]:
        base = os.environ["OPENAI_BASE_URL"]
        r = httpx.post(
            f"{base}/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]},
            timeout=5.0,
        )
        return dict(r.json())

    first = the_test()
    second = the_test()

    assert first == second
    # Upstream was hit once; second call replayed.
    assert upstream.call_count == 1

    stored = Cassette(cassette_path)
    assert len(stored) == 1


# ─── proxy_context (direct API) ────────────────────────────────────────


def test_proxy_context_yields_a_usable_handle(tmp_path: Path) -> None:
    with proxy_context(tmp_path / "tape.jsonl") as handle:
        assert handle.port > 0
        assert handle.base_url.startswith("http://127.0.0.1:")
        r = httpx.get(f"{handle.base_url}/health", timeout=2.0)
        assert r.status_code == 200


def test_proxy_context_shuts_down_cleanly(tmp_path: Path) -> None:
    """After the context exits, the server stops accepting connections."""
    with proxy_context(tmp_path / "tape.jsonl") as handle:
        port = handle.port
        # Confirm reachable
        assert httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0).status_code == 200

    # Now it should be gone. Allow a small grace period.
    import time

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.3)
            time.sleep(0.05)
            continue
        except httpx.HTTPError:
            return  # server is gone — good
    pytest.fail(f"proxy on :{port} did not shut down within 3s")
