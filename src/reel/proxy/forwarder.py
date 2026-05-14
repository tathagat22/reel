"""HTTP forwarding primitives.

The forwarder is split into three layers so record / replay / auto modes can
share them without re-reading the request body:

1. :func:`forward_with_body` — given a pre-extracted (method, path, query,
   headers, body), return a :class:`ForwardResult` (status, headers, body).
2. :func:`response_from_result` — turn a result back into a Starlette
   :class:`Response`.
3. :func:`forward_request` — convenience that ties the two together for the
   plain transparent-proxy code path.

Sprint 1.2 ships non-streaming forwarding only. Streaming (SSE) replaces the
buffered path in Sprint 2.1 and adds chunk capture for replay.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class ForwardResult:
    """The byte-level outcome of one upstream call."""

    request_body: bytes
    response_status: int
    response_body: bytes
    response_headers: dict[str, str]
    response_media_type: str | None


def _strip_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP | {"host"}}


def _strip_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in RESPONSE_STRIP}


def _build_upstream_url(upstream: Upstream, path: str, query: str) -> str:
    target = upstream.base_url.rstrip("/") + path
    if query:
        target = f"{target}?{query}"
    return target


async def forward_with_body(
    *,
    method: str,
    path: str,
    query: str,
    headers: Mapping[str, str],
    body: bytes,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
) -> ForwardResult:
    """Forward one pre-extracted request upstream and return the captured result."""
    target = _build_upstream_url(upstream, path, query)
    filtered = _strip_request_headers(headers)

    try:
        upstream_resp = await http_client.request(
            method,
            target,
            headers=filtered,
            content=body,
        )
    except httpx.HTTPError as exc:
        err_body = json.dumps(
            {
                "error": "reel: upstream request failed",
                "detail": str(exc),
                "upstream": target,
            }
        ).encode("utf-8")
        return ForwardResult(
            request_body=body,
            response_status=502,
            response_body=err_body,
            response_headers={"content-type": "application/json"},
            response_media_type="application/json",
        )

    return ForwardResult(
        request_body=body,
        response_status=upstream_resp.status_code,
        response_body=upstream_resp.content,
        response_headers=_strip_response_headers(upstream_resp.headers),
        response_media_type=upstream_resp.headers.get("content-type"),
    )


def response_from_result(result: ForwardResult) -> Response:
    """Build a Starlette :class:`Response` from a :class:`ForwardResult`."""
    return Response(
        content=result.response_body,
        status_code=result.response_status,
        headers=result.response_headers,
        media_type=result.response_media_type,
    )


async def forward_request(
    request: Request,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
) -> Response:
    """Convenience entry point — transparent forward (no capture, no replay)."""
    body = await request.body()
    result = await forward_with_body(
        method=request.method,
        path=request.url.path,
        query=request.url.query.decode("ascii") if isinstance(request.url.query, bytes) else str(
            request.url.query
        ),
        headers=request.headers,
        body=body,
        http_client=http_client,
        upstream=upstream,
    )
    return response_from_result(result)


async def proxy(request: Request) -> Response:
    """Starlette catch-all handler — dispatches to the configured mode."""
    # Import inside the handler to avoid an import cycle with proxy/modes/__init__.py
    # (modes themselves import from forwarder).
    from reel.proxy.modes import dispatch

    app = request.app
    router: Router = app.state.router

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

    return await dispatch(request, upstream)
