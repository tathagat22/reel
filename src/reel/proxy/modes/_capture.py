"""Shared upstream → cassette capture helpers used by record and auto modes.

Splitting these out keeps record.py and auto.py focused on their *dispatch*
rules (always-capture vs. replay-or-capture) and centralizes the
forward-and-record machinery in one place.
"""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from reel.cassette.body import parse_for_storage
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.store import Cassette
from reel.cassette.writer import generate_id, now_iso
from reel.proxy.forwarder import forward_with_body, response_from_result
from reel.proxy.router import Upstream
from reel.proxy.stream import (
    StreamingCapture,
    is_sse_response,
    open_streaming_upstream,
    read_all_and_close,
    stream_and_capture,
)


async def capture_buffered(
    request: Request,
    body: bytes,
    fingerprint: str,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    """Forward a non-streaming request upstream and store the exchange."""
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


async def capture_streaming(
    request: Request,
    body: bytes,
    fingerprint: str,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    """Forward a streaming request and persist the captured chunks on clean completion.

    Defensive fallback: if the upstream returns a non-SSE content-type (e.g.,
    a JSON 429 error in response to ``stream: true``), drain the body and
    persist a buffered cassette entry instead. Otherwise the cassette would
    record zero chunks and the next replay would serve an empty stream.
    """
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

    if not is_sse_response(capture.response_media_type):
        body_bytes = await read_all_and_close(upstream_resp)
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
                status=capture.response_status,
                headers=capture.response_headers,
                body=parse_for_storage(body_bytes),
            ),
        )
        await cassette.append(entry)
        return Response(
            content=body_bytes,
            status_code=capture.response_status,
            headers=capture.response_headers,
            media_type=capture.response_media_type,
        )

    async def stream_then_persist():
        async for chunk in stream_and_capture(upstream_resp, capture):
            yield chunk
        # Partial captures (client disconnect, upstream error mid-stream)
        # would poison the cassette on next replay — only persist on
        # clean upstream completion.
        if capture.completed:
            await cassette.append(
                _build_streaming_entry(request, body, fingerprint, upstream, capture)
            )

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
