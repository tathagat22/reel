"""Record mode: always forward and capture, never replay."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response

from reel.cassette.store import Cassette
from reel.proxy.modes._capture import capture_buffered, capture_streaming
from reel.proxy.router import Upstream
from reel.proxy.stream import is_streaming_request


async def record(
    request: Request,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    """Forward upstream, persist the exchange, return the upstream response."""
    body = await request.body()
    fingerprint = upstream.adapter.fingerprint(body, endpoint=request.url.path)

    if is_streaming_request(body):
        return await capture_streaming(request, body, fingerprint, http_client, upstream, cassette)
    return await capture_buffered(request, body, fingerprint, http_client, upstream, cassette)
