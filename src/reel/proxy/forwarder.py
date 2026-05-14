"""Transparent HTTP forwarding to the upstream.

Sprint 1.2 ships a *non-streaming* forwarder: it fully buffers the upstream
response before returning it. Streaming (SSE) replaces the buffered path in
Sprint 2 and adds chunk-level capture for replay.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from reel.proxy.router import Router, Upstream

# RFC 7230 §6.1 hop-by-hop headers. We must not forward these between the
# client and the upstream — they describe the per-connection link, not the
# message itself.
HOP_BY_HOP: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

# On the way *out* to the client we also strip `Host` (set by the ASGI server)
# and length/encoding fields that httpx already accounted for when buffering.
RESPONSE_STRIP: frozenset[str] = HOP_BY_HOP | frozenset({"content-encoding", "content-length"})


def _strip_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP | {"host"}}


def _strip_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in RESPONSE_STRIP}


def _build_upstream_url(upstream: Upstream, request: Request) -> str:
    target = upstream.base_url.rstrip("/") + request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return target


async def forward_request(
    request: Request,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
) -> Response:
    """Forward one request upstream, return the response. Non-streaming."""
    target = _build_upstream_url(upstream, request)
    headers = _strip_request_headers(request.headers)
    body = await request.body()

    try:
        upstream_resp = await http_client.request(
            request.method,
            target,
            headers=headers,
            content=body,
        )
    except httpx.HTTPError as exc:
        return JSONResponse(
            {
                "error": "reel: upstream request failed",
                "detail": str(exc),
                "upstream": target,
            },
            status_code=502,
        )

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=_strip_response_headers(upstream_resp.headers),
        media_type=upstream_resp.headers.get("content-type"),
    )


async def proxy(request: Request) -> Response:
    """Starlette catch-all handler. Routes via :class:`Router`, forwards otherwise."""
    app = request.app
    router: Router = app.state.router
    http_client: httpx.AsyncClient = app.state.http_client

    upstream = router.resolve(request.url.path)
    if upstream is None:
        return JSONResponse(
            {
                "error": "reel: no upstream configured for this path",
                "path": request.url.path,
                "hint": "Reel proxies LLM endpoints. Point your SDK at a known path "
                f"(allowed prefixes: {list(router.allowed_prefixes)}).",
            },
            status_code=404,
        )

    return await forward_request(request, http_client, upstream)
