"""Cassette entry filtering.

One immutable :class:`FilterSpec`, one streaming :func:`apply` — built so a
caller passing five flags pays one pass through the cassette, not five.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, cast

from reel.cassette.schema import CassetteEntry


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """Composable filter for cassette entries.

    Each non-``None`` field contributes one AND-clause; an entry passes only
    if every active clause matches. ``limit`` is applied last as a streaming
    head-cut.
    """

    provider: str | None = None
    model: str | None = None
    status: str | None = None  # "2xx", "4xx", "5xx", or exact like "429"
    has_tool_call: bool | None = None
    regex: re.Pattern[str] | None = None
    limit: int | None = None


def apply(spec: FilterSpec, entries: Iterable[CassetteEntry]) -> Iterator[CassetteEntry]:
    """Yield entries matching every active predicate in ``spec``.

    Single-pass; short-circuits per entry; honors ``limit`` lazily.
    """
    emitted = 0
    for entry in entries:
        if spec.provider is not None and entry.provider != spec.provider:
            continue
        if spec.model is not None and not _model_matches(entry, spec.model):
            continue
        if spec.status is not None and not _status_matches(entry, spec.status):
            continue
        if spec.has_tool_call is not None and _has_tool_call(entry) != spec.has_tool_call:
            continue
        if spec.regex is not None and not _regex_matches(entry, spec.regex):
            continue

        yield entry
        emitted += 1
        if spec.limit is not None and emitted >= spec.limit:
            return


# ─── Predicate helpers ─────────────────────────────────────────────────


def _model_matches(entry: CassetteEntry, needle: str) -> bool:
    """Substring (case-insensitive) match against the request body's ``model``."""
    body = entry.request.body
    if not isinstance(body, dict):
        return False
    model = cast(dict[str, Any], body).get("model")
    if not isinstance(model, str):
        return False
    return needle.lower() in model.lower()


def _status_matches(entry: CassetteEntry, status: str) -> bool:
    """Match exact (``"429"``) or class (``"2xx"`` / ``"4xx"`` / ``"5xx"``)."""
    s = status.lower()
    code = entry.response.status
    if s.endswith("xx") and len(s) == 3 and s[0].isdigit():
        return code // 100 == int(s[0])
    if s.isdigit():
        return code == int(s)
    return False


def _has_tool_call(entry: CassetteEntry) -> bool:
    """``True`` if the request defines tools OR the response contains tool_calls."""
    req_body = entry.request.body
    if isinstance(req_body, dict):
        rb = cast(dict[str, Any], req_body)
        if rb.get("tools") or rb.get("functions"):
            return True
    return _response_has_tool_calls(entry.response.body) or _stream_has_tool_calls(entry)


def _response_has_tool_calls(body: Any) -> bool:
    """Cheap structural walk — short-circuits on the first ``tool_calls`` / ``function_call``."""
    if isinstance(body, dict):
        d = cast(dict[str, Any], body)
        if "tool_calls" in d or "function_call" in d:
            return True
        return any(_response_has_tool_calls(v) for v in d.values())
    if isinstance(body, list):
        return any(_response_has_tool_calls(v) for v in cast(list[Any], body))
    return False


def _stream_has_tool_calls(entry: CassetteEntry) -> bool:
    chunks = entry.response.stream_chunks
    if chunks is None:
        return False
    return any(_response_has_tool_calls(c.data) for c in chunks)


def _regex_matches(entry: CassetteEntry, pattern: re.Pattern[str]) -> bool:
    """Regex search over the JSON-serialized entry (so it scans bodies + headers)."""
    return pattern.search(entry.model_dump_json()) is not None
