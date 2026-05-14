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
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from reel.proxy.config import ProxyConfig
from reel.proxy.logs import emit as emit_log
from reel.proxy.router import Resolution, Router, Upstream

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


def strip_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Drop hop-by-hop headers (and ``Host``) before forwarding upstream."""
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP | {"host"}}


def strip_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Drop hop-by-hop and length/encoding headers from an upstream response."""
    return {k: v for k, v in headers.items() if k.lower() not in RESPONSE_STRIP}


def build_upstream_url(upstream: Upstream, path: str, query: str) -> str:
    """Compose an absolute upstream URL from path + query."""
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
    target = build_upstream_url(upstream, path, query)
    filtered = strip_request_headers(headers)

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
        response_headers=strip_response_headers(upstream_resp.headers),
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
        query=request.url.query.decode("ascii")
        if isinstance(request.url.query, bytes)
        else str(request.url.query),
        headers=request.headers,
        body=body,
        http_client=http_client,
        upstream=upstream,
    )
    return response_from_result(result)


async def proxy(request: Request) -> Response:
    """Starlette catch-all handler — dispatches to the configured mode.

    Wraps the dispatch in start/end timing so every request emits exactly one
    structured log line (text or JSON, configured at startup).
    """
    # Import inside the handler to avoid an import cycle with proxy/modes/__init__.py
    # (modes themselves import from forwarder).
    from reel.proxy.modes import dispatch

    app = request.app
    config: ProxyConfig = app.state.config
    router: Router = app.state.router

    started = time.monotonic()
    request_method = request.method
    request_path = request.url.path

    resolution = router.resolve(request_path)
    if resolution is None:
        response = JSONResponse(
            {
                "error": "reel: no upstream configured for this path",
                "path": request_path,
                "hint": "Reel proxies LLM endpoints. Point your SDK at a known path "
                f"(allowed prefixes: {list(router.allowed_prefixes)}).",
            },
            status_code=404,
        )
        _log_request(config, started, None, request_method, request_path, response.status_code)
        return response

    # Rewrite the ASGI scope so downstream readers of request.url.path see the
    # upstream-facing path (with the optional /<provider>/ prefix stripped).
    # `Request.url` is cached on first access, so we also invalidate it.
    if resolution.rewritten_path != request_path:
        request.scope["path"] = resolution.rewritten_path
        request.scope["raw_path"] = resolution.rewritten_path.encode("ascii")
        if hasattr(request, "_url"):
            delattr(request, "_url")

    response = await dispatch(request, resolution.upstream)
    _log_request(config, started, resolution, request_method, request_path, response.status_code)
    return response


def _log_request(
    config: ProxyConfig,
    started: float,
    resolution: Resolution | None,
    method: str,
    path: str,
    status: int,
) -> None:
    """Build one log event for the just-completed request."""
    emit_log(
        {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "mode": config.mode,
            "provider": resolution.upstream.provider if resolution is not None else None,
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": int((time.monotonic() - started) * 1000),
        },
        log_format=config.log_format,
    )
