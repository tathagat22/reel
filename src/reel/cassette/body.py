"""Cassette body codec.

Request and response bodies are stored in a JSON-friendly form so cassette
diffs are reviewable. JSON payloads are stored as parsed objects; anything
else (audio, multipart, binary) is wrapped in a base64 envelope. The codec
is fully round-trippable.
"""

from __future__ import annotations

import base64
import json
from typing import Any, cast

# Sentinel key marking a base64-encoded raw body.
RAW_KEY = "__reel_raw_base64__"


def parse_for_storage(body: bytes) -> Any:
    """Convert raw bytes into a JSON-serializable cassette body."""
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {RAW_KEY: base64.b64encode(body).decode("ascii")}


def serialize_from_storage(stored: Any) -> bytes:
    """Reverse :func:`parse_for_storage`."""
    if stored is None:
        return b""
    if isinstance(stored, dict) and RAW_KEY in stored:
        d = cast(dict[str, Any], stored)
        encoded: Any = d[RAW_KEY]
        if not isinstance(encoded, str):
            raise TypeError(f"{RAW_KEY} value must be a string, got {type(encoded).__name__}")
        return base64.b64decode(encoded)
    if isinstance(stored, (dict, list, bool, int, float)):
        return json.dumps(stored).encode("utf-8")
    if isinstance(stored, str):
        return stored.encode("utf-8")
    raise TypeError(f"unexpected stored body type: {type(stored).__name__}")


def parse_sse_data(value: str) -> Any:
    """Parse an SSE ``data:`` payload into a JSON-friendly cassette form.

    Differs from :func:`parse_for_storage` because SSE payloads are always
    text — no base64 envelope needed for non-JSON values like ``"[DONE]"``.
    """
    if not value:
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def serialize_sse_data(stored: Any) -> str:
    """Reverse :func:`parse_sse_data` — produce the string for ``data: <here>``."""
    if isinstance(stored, str):
        return stored
    return json.dumps(stored)
