"""Auto mode: replay if the cassette has a match, otherwise record.

This is the default for local dev loops — first run captures every request,
subsequent runs are cost-free and offline.
"""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response

from reel.adapters.openai import fingerprint as openai_fingerprint
from reel.cassette.body import parse_for_storage
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.store import Cassette
from reel.cassette.writer import generate_id, now_iso
from reel.proxy.forwarder import forward_with_body, response_from_result
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
    fp = openai_fingerprint(body, endpoint=request.url.path)

    existing = cassette.find(fp)
    if existing is not None:
        return response_from_entry(existing)

    # Cache miss: forward and capture.
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
            fingerprint=fp,
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
