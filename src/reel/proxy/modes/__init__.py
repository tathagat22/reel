"""Mode dispatcher.

The proxy's behavior — *forward and capture*, *serve from cassette*, or
*both* — is selected by :attr:`reel.proxy.config.ProxyConfig.mode`.

Modes share a single signature so the catch-all handler can hand off without
caring which mode is active.
"""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.modes.record import record
from reel.proxy.router import Upstream

__all__ = ["dispatch", "record"]


def _no_cassette_error(mode: str) -> JSONResponse:
    return JSONResponse(
        {
            "error": f"reel: {mode!r} mode requires --cassette",
            "hint": "Pass --cassette <path> or set REEL_CASSETTE before starting the proxy.",
        },
        status_code=400,
    )


def _not_implemented(mode: str) -> JSONResponse:
    return JSONResponse(
        {
            "error": f"reel: {mode!r} mode is not implemented yet",
            "hint": "record mode lands in Sprint 1.6; replay in 1.7; auto in 1.8.",
        },
        status_code=501,
    )


async def dispatch(request: Request, upstream: Upstream) -> Response:
    """Hand off to the configured mode."""
    app = request.app
    config: ProxyConfig = app.state.config
    http_client: httpx.AsyncClient = app.state.http_client
    cassette: Cassette | None = getattr(app.state, "cassette", None)

    if config.mode == "record":
        if cassette is None:
            return _no_cassette_error("record")
        return await record(request, http_client, upstream, cassette)

    if config.mode in ("replay", "auto"):
        return _not_implemented(config.mode)

    # Unreachable — ProxyConfig validates mode at construction.
    return JSONResponse({"error": f"reel: unknown mode {config.mode!r}"}, status_code=500)
