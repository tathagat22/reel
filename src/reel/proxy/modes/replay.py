"""Replay mode: serve responses entirely from the cassette.

Replay never touches the network. A request whose fingerprint isn't in the
cassette responds with **404** — loud failure beats silent regression in tests.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from reel.adapters.openai import fingerprint as openai_fingerprint
from reel.cassette.body import serialize_from_storage
from reel.cassette.schema import CassetteEntry
from reel.cassette.store import Cassette


async def replay(request: Request, cassette: Cassette) -> Response:
    """Look up the cassette by fingerprint and return the stored response."""
    body = await request.body()
    fp = openai_fingerprint(body, endpoint=request.url.path)

    entry = cassette.find(fp)
    if entry is None:
        return JSONResponse(
            {
                "error": "reel: no cassette entry matches this request",
                "fingerprint": fp,
                "path": request.url.path,
                "hint": (
                    "Switch to 'auto' or 'record' mode to capture this request, "
                    f"or check that the cassette ({cassette.path}) contains it."
                ),
            },
            status_code=404,
        )

    return response_from_entry(entry)


def response_from_entry(entry: CassetteEntry) -> Response:
    """Materialize a stored entry back into a Starlette Response.

    Shared between :mod:`reel.proxy.modes.replay` and
    :mod:`reel.proxy.modes.auto`.
    """
    body = serialize_from_storage(entry.response.body)
    return Response(
        content=body,
        status_code=entry.response.status,
        headers=entry.response.headers,
        media_type=entry.response.headers.get("content-type"),
    )
