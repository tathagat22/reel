"""The ``@cassette`` decorator — drop Reel into any test in one line.

::

    from reel import cassette

    @cassette("tests/cassettes/test_summarize.jsonl")
    def test_summarize() -> None:
        client = OpenAI()  # reads OPENAI_BASE_URL set by the decorator
        resp = client.chat.completions.create(model="gpt-5", messages=[...])
        assert "TL;DR" in resp.choices[0].message.content

The decorator spins up a real Reel proxy on a free local port for the
duration of the test, points the OpenAI / Anthropic / Gemini SDK base URLs
at it (so your existing test code doesn't change), and tears it down when
the test exits. First run captures real upstream responses into the
cassette; every subsequent run replays them with zero network and zero cost.

Compatible with sync and async tests via the corresponding decorator forms.
"""

from __future__ import annotations

import functools
import socket
import threading
import time
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

import uvicorn

from reel.proxy.config import Mode, ProxyConfig
from reel.proxy.server import create_app

P = ParamSpec("P")
R = TypeVar("R")

# Env-var keys we shadow during the cassette context.
_ENV_KEYS_TO_OVERRIDE: tuple[tuple[str, str], ...] = (
    ("OPENAI_BASE_URL", "/v1"),
    ("OPENAI_API_BASE", "/v1"),  # legacy SDK env name
    ("ANTHROPIC_BASE_URL", ""),
    ("GOOGLE_GEMINI_BASE_URL", "/v1beta"),
    ("GEMINI_BASE_URL", "/v1beta"),
)


def cassette(
    path: str | Path,
    *,
    mode: Mode = "auto",
    redact_pii: bool = True,
    startup_timeout: float = 5.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Wrap a (sync or async) test function so Reel proxies its LLM calls.

    Args:
        path: Where the JSONL cassette lives. Auto-created on first run.
        mode: ``"auto"`` (default), ``"record"``, or ``"replay"``.
        redact_pii: Scrub email/phone patterns from captured responses.
        startup_timeout: Seconds to wait for the proxy to become reachable.
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        if _is_coroutine_function(fn):
            async_fn = cast(Callable[P, Awaitable[Any]], fn)
            wrapped_async = _wrap_async(async_fn, path, mode, redact_pii, startup_timeout)
            return cast(Callable[P, R], wrapped_async)
        return _wrap_sync(fn, path, mode, redact_pii, startup_timeout)

    return decorator


# ─── Implementation ────────────────────────────────────────────────────


def _is_coroutine_function(fn: Callable[..., Any]) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)


def _wrap_sync(
    fn: Callable[P, R],
    path: str | Path,
    mode: Mode,
    redact_pii: bool,
    startup_timeout: float,
) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with proxy_context(path, mode=mode, redact_pii=redact_pii, startup_timeout=startup_timeout):
            return fn(*args, **kwargs)

    return wrapper


def _wrap_async(
    fn: Callable[P, Awaitable[R]],
    path: str | Path,
    mode: Mode,
    redact_pii: bool,
    startup_timeout: float,
) -> Callable[P, Awaitable[R]]:
    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with proxy_context(path, mode=mode, redact_pii=redact_pii, startup_timeout=startup_timeout):
            return await fn(*args, **kwargs)

    return wrapper


@contextmanager
def proxy_context(
    cassette_path: str | Path,
    *,
    mode: Mode = "auto",
    redact_pii: bool = True,
    startup_timeout: float = 5.0,
) -> Generator[ProxyHandle]:
    """Programmatic equivalent of ``@cassette`` — usable from non-pytest code."""
    port = _find_free_port()
    cfg = ProxyConfig(
        host="127.0.0.1",
        port=port,
        mode=mode,
        cassette_path=str(cassette_path),
        redact_pii=redact_pii,
    )
    app = create_app(cfg)

    uvi_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(uvi_config)
    # uvicorn installs signal handlers on the main thread by default.
    # We're running in a worker thread, so disable them.
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    thread = threading.Thread(target=server.run, daemon=True, name=f"reel-proxy-{port}")
    thread.start()

    try:
        _wait_for_ready(port, timeout=startup_timeout)
        with _patched_env(port):
            yield ProxyHandle(port=port, cassette_path=Path(str(cassette_path)))
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)


class ProxyHandle:
    """Returned from :func:`proxy_context` — useful for tests that want the URL."""

    __slots__ = ("cassette_path", "port")

    def __init__(self, *, port: int, cassette_path: Path) -> None:
        self.port = port
        self.cassette_path = cassette_path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


def _wait_for_ready(port: int, *, timeout: float) -> None:
    """Wait until TCP connect succeeds on the port.

    Uses a raw socket (not httpx) so user-level test mocks like ``respx``
    don't intercept the readiness check.
    """
    start = time.monotonic()
    last_err: Exception | None = None
    while time.monotonic() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.02)
    raise TimeoutError(
        f"reel proxy on :{port} didn't become ready in {timeout}s (last error: {last_err!r})"
    )


@contextmanager
def _patched_env(port: int) -> Generator[None]:
    """Override LLM SDK base-URL env vars; restore on exit."""
    import os

    base = f"http://127.0.0.1:{port}"
    saved: dict[str, str | None] = {}
    for key, suffix in _ENV_KEYS_TO_OVERRIDE:
        saved[key] = os.environ.get(key)
        os.environ[key] = base + suffix
    try:
        yield
    finally:
        for key, _ in _ENV_KEYS_TO_OVERRIDE:
            prior = saved.get(key)
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
