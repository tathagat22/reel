"""Structured request logging.

Two formats:

* ``text`` (default) — one rich-printable line per request, optimized for human eyes.
* ``json`` — one JSON object per line, suitable for ``jq``, ``fluentd``, or journald ingestion.

Emission happens exactly once per request inside the catch-all proxy handler —
every mode (record / replay / auto) funnels through there, so there's no
duplicated logging logic in the mode-specific files.

Reel suppresses uvicorn's own access log (``access_log=False``,
``log_level="error"``), so stdout carries only these events.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any, Literal

LogFormat = Literal["text", "json"]


def emit(event: Mapping[str, Any], *, log_format: LogFormat) -> None:
    """Write one log event to stdout. ``json`` is compact, ``text`` is human-readable.

    Fetches :data:`sys.stdout` per call so test harnesses (``capsys``,
    ``contextlib.redirect_stdout``) can capture output even when the proxy
    server started before they did.
    """
    out = sys.stdout
    if log_format == "json":
        out.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False))
    else:
        out.write(_format_text(event))
    out.write("\n")
    out.flush()


def _format_text(event: Mapping[str, Any]) -> str:
    """One-line, fixed-order, human-scannable rendering."""
    ts = str(event.get("ts", "-")).split("T", 1)[-1].split("+", 1)[0]
    mode = event.get("mode", "?")
    provider = event.get("provider") or "-"
    method = event.get("method", "?")
    path = event.get("path", "?")
    status = event.get("status", "?")
    duration = event.get("duration_ms")
    duration_part = f" {duration}ms" if duration is not None else ""
    return f"{ts} [{mode}] {provider} {method} {path} -> {status}{duration_part}"
