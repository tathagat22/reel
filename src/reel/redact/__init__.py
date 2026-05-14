"""Secret and PII redaction for cassettes.

The top-level :func:`redact_entry` walks a :class:`CassetteEntry`'s response
side (headers, body, stream chunks) and scrubs detected secrets and (by
default) PII. The request side is **not** scrubbed because Reel never
captures request headers in the first place — the only place secrets could
land is in a recorded response.
"""

from __future__ import annotations

from typing import Any, cast

from reel.cassette.schema import CassetteEntry, CassetteResponse, StreamChunk
from reel.redact.pii import contains_pii, redact_pii
from reel.redact.secrets import contains_secret, redact_secrets

__all__ = [
    "contains_pii",
    "contains_secret",
    "redact_entry",
    "redact_pii",
    "redact_secrets",
]


def redact_entry(entry: CassetteEntry, *, scrub_pii: bool = True) -> CassetteEntry:
    """Return a copy of ``entry`` with secrets (and optionally PII) scrubbed."""
    new_headers = {
        k: _scrub_text(v, scrub_pii=scrub_pii) for k, v in entry.response.headers.items()
    }
    new_body = _scrub_any(entry.response.body, scrub_pii=scrub_pii)
    new_chunks: list[StreamChunk] | None = None
    if entry.response.stream_chunks is not None:
        new_chunks = [
            StreamChunk(
                data=_scrub_any(c.data, scrub_pii=scrub_pii),
                t_offset_ms=c.t_offset_ms,
                event=c.event,
            )
            for c in entry.response.stream_chunks
        ]

    return entry.model_copy(
        update={
            "response": CassetteResponse(
                status=entry.response.status,
                headers=new_headers,
                body=new_body,
                stream_chunks=new_chunks,
            )
        }
    )


def _scrub_text(text: str, *, scrub_pii: bool) -> str:
    out = redact_secrets(text)
    if scrub_pii:
        out = redact_pii(out)
    return out


def _scrub_any(value: Any, *, scrub_pii: bool) -> Any:
    """Walk dict / list / string recursively. Non-text scalars pass through."""
    if value is None:
        return None
    if isinstance(value, str):
        return _scrub_text(value, scrub_pii=scrub_pii)
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        return {k: _scrub_any(v, scrub_pii=scrub_pii) for k, v in d.items()}
    if isinstance(value, list):
        lst = cast(list[Any], value)
        return [_scrub_any(v, scrub_pii=scrub_pii) for v in lst]
    return value
