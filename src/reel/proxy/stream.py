"""Streaming forwarder primitives.

A streaming upstream call is a two-step dance:

1. :func:`open_streaming_upstream` opens the connection and returns the open
   :class:`httpx.Response` together with a :class:`StreamingCapture` whose
   status and headers are already filled in. The caller can build the
   client-facing :class:`starlette.responses.StreamingResponse` *before*
   iterating the body — that's why we split this from the actual byte iteration.
2. :func:`stream_and_capture` yields the body bytes to the client while
   incrementally parsing the SSE stream and recording each event with a
   timing offset into the capture.

The split design lets record / replay / auto wire the same primitives
without re-reading the body or re-opening upstream connections.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from reel.cassette.body import parse_sse_data
from reel.cassette.schema import StreamChunk
from reel.proxy.forwarder import build_upstream_url, strip_request_headers, strip_response_headers
from reel.proxy.router import Upstream
from reel.proxy.sse import SSEParser


@dataclass(slots=True)
class StreamingCapture:
    """Mutable state collected from one streaming upstream call."""

    request_body: bytes
    response_status: int
    response_headers: dict[str, str]
    response_media_type: str | None
    chunks: list[StreamChunk] = field(default_factory=lambda: cast(list[StreamChunk], []))
    completed: bool = False
    """``True`` once the upstream stream finished cleanly. Stays ``False``
    on client disconnect or upstream error so partial captures aren't
    written to the cassette."""


def is_streaming_request(body: bytes) -> bool:
    """Best-effort detection: is the JSON body asking for an SSE response?

    For OpenAI / Anthropic / Gemini this is ``"stream": true`` at the top
    level. Non-JSON bodies and bodies without the flag are treated as
    non-streaming (the buffered forwarder handles them).
    """
    if not body:
        return False
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    return cast(dict[str, Any], parsed).get("stream") is True


async def open_streaming_upstream(
    *,
    method: str,
    path: str,
    query: str,
    headers: Mapping[str, str],
    body: bytes,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
) -> tuple[httpx.Response, StreamingCapture]:
    """Open the upstream stream. Returns (open response, capture)."""
    target = build_upstream_url(upstream, path, query)
    filtered = strip_request_headers(headers)

    req = http_client.build_request(method, target, headers=filtered, content=body)
    upstream_resp = await http_client.send(req, stream=True)

    capture = StreamingCapture(
        request_body=body,
        response_status=upstream_resp.status_code,
        response_headers=strip_response_headers(upstream_resp.headers),
        response_media_type=upstream_resp.headers.get("content-type"),
    )
    return upstream_resp, capture


async def stream_and_capture(
    upstream_resp: httpx.Response,
    capture: StreamingCapture,
) -> AsyncIterator[bytes]:
    """Yield body bytes to the client while capturing SSE events into ``capture``.

    Always closes the upstream response, even on client disconnect.
    """
    parser = SSEParser()
    start_time = time.monotonic()

    try:
        async for chunk in upstream_resp.aiter_bytes():
            t_offset_ms = int((time.monotonic() - start_time) * 1000)
            for event in parser.feed(chunk):
                capture.chunks.append(
                    StreamChunk(
                        data=parse_sse_data(event.data),
                        t_offset_ms=t_offset_ms,
                        event=event.event,
                    )
                )
            yield chunk

        # Stream completed without error — flush any in-progress event.
        flush_t_offset_ms = int((time.monotonic() - start_time) * 1000)
        for event in parser.close():
            capture.chunks.append(
                StreamChunk(
                    data=parse_sse_data(event.data),
                    t_offset_ms=flush_t_offset_ms,
                    event=event.event,
                )
            )
        capture.completed = True
    finally:
        await upstream_resp.aclose()
