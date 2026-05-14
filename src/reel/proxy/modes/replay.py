"""Replay mode: serve responses entirely from the cassette.

Replay never touches the network. A request whose fingerprint isn't in the
cassette responds with **404** — loud failure beats silent regression in
tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from reel.cassette.body import serialize_from_storage, serialize_sse_data
from reel.cassette.schema import CassetteEntry, StreamChunk
from reel.cassette.store import Cassette
from reel.proxy.config import ProxyConfig
from reel.proxy.router import Upstream


async def replay(request: Request, upstream: Upstream, cassette: Cassette) -> Response:
    """Look up the cassette using its configured match mode."""
    body = await request.body()
    entry = cassette.find_smart(body=body, path=request.url.path, adapter=upstream.adapter)
    if entry is None:
        return JSONResponse(
            {
                "error": "reel: no cassette entry matches this request",
                "fingerprint": upstream.adapter.fingerprint(body, endpoint=request.url.path),
                "path": request.url.path,
                "match_mode": cassette.match_config.mode,
                "hint": (
                    "Switch to 'auto' or 'record' mode to capture this request, "
                    f"or check that the cassette ({cassette.path}) contains it."
                ),
            },
            status_code=404,
        )

    config: ProxyConfig = request.app.state.config
    return response_from_entry(entry, timing_multiplier=config.replay_timing_multiplier)


def response_from_entry(entry: CassetteEntry, *, timing_multiplier: float = 1.0) -> Response:
    """Materialize a stored entry into a Starlette Response.

    Streaming entries (``stream_chunks`` set) get a :class:`StreamingResponse`
    paced by ``timing_multiplier``; buffered entries get a plain
    :class:`Response`.
    """
    if entry.response.stream_chunks is not None:
        return _streaming_response_from_entry(entry, timing_multiplier)
    return _buffered_response_from_entry(entry)


def _buffered_response_from_entry(entry: CassetteEntry) -> Response:
    body = serialize_from_storage(entry.response.body)
    return Response(
        content=body,
        status_code=entry.response.status,
        headers=entry.response.headers,
        media_type=entry.response.headers.get("content-type"),
    )


def _streaming_response_from_entry(
    entry: CassetteEntry, timing_multiplier: float
) -> StreamingResponse:
    chunks: list[StreamChunk] = entry.response.stream_chunks or []

    async def gen() -> AsyncIterator[bytes]:
        prev_offset_ms = 0
        for chunk in chunks:
            delta_ms = max(0, chunk.t_offset_ms - prev_offset_ms)
            sleep_s = (delta_ms / 1000.0) * timing_multiplier
            if sleep_s > 0:
                await asyncio.sleep(sleep_s)
            yield _serialize_sse_chunk(chunk)
            prev_offset_ms = chunk.t_offset_ms

    return StreamingResponse(
        gen(),
        status_code=entry.response.status,
        headers=entry.response.headers,
        media_type=entry.response.headers.get("content-type", "text/event-stream"),
    )


def _serialize_sse_chunk(chunk: StreamChunk) -> bytes:
    """Reconstruct one SSE frame: optional ``event:`` plus one or more ``data:`` lines."""
    lines: list[str] = []
    if chunk.event is not None:
        lines.append(f"event: {chunk.event}")
    data_str = serialize_sse_data(chunk.data)
    # SSE multi-line data: one `data:` field per line, joined with \n by the parser.
    for data_line in data_str.split("\n"):
        lines.append(f"data: {data_line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")
