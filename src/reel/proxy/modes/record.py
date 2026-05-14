"""Record mode: forward to upstream, capture both sides into the cassette."""

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
from reel.proxy.router import Upstream


async def record(
    request: Request,
    http_client: httpx.AsyncClient,
    upstream: Upstream,
    cassette: Cassette,
) -> Response:
    """Forward upstream, persist the exchange, return the upstream response.

    The cassette captures method, path, fingerprint, and bodies. *Request
    headers are intentionally not stored* — they typically contain API keys
    and have no value for replay matching.
    """
    body = await request.body()
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

    fp = openai_fingerprint(body, endpoint=request.url.path)
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
