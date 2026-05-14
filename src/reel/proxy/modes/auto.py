"""Auto mode: replay if the cassette has a match, otherwise record."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response

from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.modes._capture import capture_buffered, capture_streaming
from reel.proxy.modes.replay import response_from_entry
from reel.proxy.router import Upstream


async def auto(
    request: Request,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    """Replay if fingerprint matches; otherwise forward upstream and record."""
    body = await request.body()
    fingerprint = upstream.adapter.fingerprint(body, endpoint=request.url.path)

    existing = cassette.find(fingerprint)
    if existing is not None:
        config: ProxyConfig = request.app.state.config
        return response_from_entry(existing, timing_multiplier=config.replay_timing_multiplier)

    # Cache miss: forward and capture.
    if upstream.adapter.is_streaming(request.url.path, body):
        return await capture_streaming(request, body, fingerprint, http_client, upstream, cassette)
    return await capture_buffered(request, body, fingerprint, http_client, upstream, cassette)
