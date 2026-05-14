"""Reel proxy core.

The bare HTTP server for Sprint 1.1. Routing, recording, and replay are wired
in later tasks (1.2-1.8). This module's only job today is:

* Spin up a starlette ASGI app with an httpx.AsyncClient managed by lifespan.
* Expose ``/health`` for liveness.
* Provide ``serve()`` so the CLI and tests can launch the proxy uniformly.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from reel import __version__
from reel.proxy.config import ProxyConfig

HTTP_CLIENT_KEY = "reel.http_client"
CONFIG_KEY = "reel.config"


async def health(request: Request) -> Response:
    """Liveness probe. Returns 200 with the proxy version + mode."""
    config: ProxyConfig = request.app.state.config
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "mode": config.mode,
            "cassette": config.cassette_path,
        }
    )


@asynccontextmanager
async def _lifespan(app: Starlette, config: ProxyConfig) -> AsyncGenerator[None]:
    """ASGI lifespan: own a single shared httpx client for the proxy's lifetime."""
    timeout = httpx.Timeout(config.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.http_client = client
        app.state.config = config
        yield


def create_app(config: ProxyConfig | None = None) -> Starlette:
    """Build the ASGI app. Sprint 1.1 wires `/health` only."""
    cfg = config or ProxyConfig.from_env()
    routes = [Route("/health", health, methods=["GET"])]
    app = Starlette(
        routes=routes,
        lifespan=functools.partial(_lifespan, config=cfg),
    )
    app.state.config = cfg
    return app


def serve(config: ProxyConfig | None = None) -> None:
    """Run the proxy synchronously (blocks the calling thread)."""
    cfg = config or ProxyConfig.from_env()
    app = create_app(cfg)
    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level="info",
        access_log=False,
    )
