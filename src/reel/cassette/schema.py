"""Cassette JSONL schema.

One JSON object per line. Designed to be:

* **Diff-friendly** in PRs — JSON-encoded bodies are stored parsed (when valid
  JSON) so reviewers see the actual prompt/response text, not opaque blobs.
* **Greppable** — search a cassette with ``grep`` without parsing.
* **Append-safe** — appending never rewrites earlier lines.
* **Forward-compatible** — unknown future fields are rejected during validation
  to keep authors honest about schema evolution. Each schema bump increments
  ``SCHEMA_VERSION`` and ``CassetteEntry.schema_version``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class CassetteRequest(BaseModel):
    """Captured request side of an exchange."""

    model_config = ConfigDict(extra="forbid")

    method: str
    path: str
    fingerprint: str
    body: Any = None
    """Parsed JSON (preferred) or a ``{"__reel_raw_base64__": str}`` envelope for
    non-JSON bodies. ``None`` means the request had no body."""


class StreamChunk(BaseModel):
    """One captured SSE event from a streaming upstream response.

    ``data`` is stored in a diff-friendly form: parsed JSON when the SSE
    payload was valid JSON, otherwise the raw string (e.g., ``"[DONE]"``).
    """

    model_config = ConfigDict(extra="forbid")

    data: Any
    t_offset_ms: int
    """Milliseconds from the first byte of the upstream response."""
    event: str | None = None
    """SSE ``event:`` field if the upstream set one (Anthropic uses these;
    OpenAI doesn't)."""


class CassetteResponse(BaseModel):
    """Captured response side of an exchange."""

    model_config = ConfigDict(extra="forbid")

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    """Buffered response body. Same convention as
    :py:attr:`CassetteRequest.body`. Set to ``None`` for streaming responses
    — :py:attr:`stream_chunks` carries them instead."""
    stream_chunks: list[StreamChunk] | None = None
    """Captured SSE events for streaming responses, with timing offsets that
    let replay reproduce TTFT and inter-chunk gaps."""


class CassetteEntry(BaseModel):
    """A single recorded request/response exchange."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    id: str
    ts: str
    """ISO 8601 UTC timestamp of the capture (e.g., ``2026-05-15T10:23:11Z``)."""
    provider: str
    request: CassetteRequest
    response: CassetteResponse
    meta: dict[str, Any] = Field(default_factory=dict)
    """Free-form metadata bag — tokens, cost, timings. Sprint 5 fills this in."""
