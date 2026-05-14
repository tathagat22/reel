"""Record mode: forward to upstream, capture both sides into the cassette."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from reel.adapters.openai import fingerprint as openai_fingerprint
from reel.cassette.body import parse_for_storage
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.store import Cassette
from reel.cassette.writer import generate_id, now_iso
from reel.proxy.forwarder import forward_with_body, response_from_result
from reel.proxy.router import Upstream
from reel.proxy.stream import (
    StreamingCapture,
    is_streaming_request,
    open_streaming_upstream,
    stream_and_capture,
)


async def record(
    request: Request,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    """Forward upstream, persist the exchange, return the upstream response.

    Dispatches to streaming or buffered capture based on whether the request
    asks for ``stream: true``. Request headers are intentionally never
    captured — they typically contain API keys.
    """
    body = await request.body()
    fp = openai_fingerprint(body, endpoint=request.url.path)

    if is_streaming_request(body):
        return await _record_streaming(request, body, fp, http_client, upstream, cassette)
    return await _record_buffered(request, body, fp, http_client, upstream, cassette)


async def _record_buffered(
    request: Request,
    body: bytes,
    fingerprint: str,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    query = str(request.url.query) if request.url.query else ""

    result = await forward_with_body(
        method=request.method,
        path=request.url.path,
        query=query,
        headers=request.headers,
        body=body,
        http_client=http_client,
        upstream=upstream,
    )

    entry = CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=upstream.provider,
        request=CassetteRequest(
            method=request.method,
            path=request.url.path,
            fingerprint=fingerprint,
            body=parse_for_storage(body),
        ),
        response=CassetteResponse(
            status=result.response_status,
            headers=result.response_headers,
            body=parse_for_storage(result.response_body),
        ),
    )
    await cassette.append(entry)

    return response_from_result(result)


async def _record_streaming(
    request: Request,
    body: bytes,
    fingerprint: str,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    query = str(request.url.query) if request.url.query else ""

    upstream_resp, capture = await open_streaming_upstream(
        method=request.method,
        path=request.url.path,
        query=query,
        headers=request.headers,
        body=body,
        http_client=http_client,
        upstream=upstream,
    )

    async def stream_then_persist():
        async for chunk in stream_and_capture(upstream_resp, capture):
            yield chunk
        # Only persist on clean completion — partial captures would poison
        # the cassette on next replay.
        if capture.completed:
            await cassette.append(_build_streaming_entry(request, body, fingerprint, upstream, capture))

    return StreamingResponse(
        stream_then_persist(),
        status_code=capture.response_status,
        headers=capture.response_headers,
        media_type=capture.response_media_type,
    )


def _build_streaming_entry(
    request: Request,
    body: bytes,
    fingerprint: str,
    upstream: Upstream,
    capture: StreamingCapture,
) -> CassetteEntry:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=upstream.provider,
        request=CassetteRequest(
            method=request.method,
            path=request.url.path,
            fingerprint=fingerprint,
            body=parse_for_storage(body),
        ),
        response=CassetteResponse(
            status=capture.response_status,
            headers=capture.response_headers,
            body=None,
            stream_chunks=capture.chunks,
        ),
    )
