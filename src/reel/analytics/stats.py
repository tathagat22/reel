"""Cassette aggregate statistics.

Pure functions over :class:`CassetteEntry` sequences. One single-pass
:func:`aggregate` walks every entry exactly once and returns an immutable
:class:`StatsSummary` with counts, error rate, token totals, and a TTFT
distribution computed only over streaming entries.

Token extraction handles three provider shapes:

* OpenAI    — ``usage.prompt_tokens`` / ``usage.completion_tokens``
* Anthropic — ``usage.input_tokens``  / ``usage.output_tokens``
* Gemini    — ``usageMetadata.promptTokenCount`` /
              ``usageMetadata.candidatesTokenCount``

For streaming entries usage typically rides on the final chunk, so we look at
the last :class:`StreamChunk`'s parsed ``data``; for non-streaming entries we
read the buffered response body directly.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

from reel.cassette.schema import CassetteEntry, StreamChunk


def _empty_str_int_dict() -> dict[str, int]:
    return {}


@dataclass(frozen=True, slots=True)
class TTFTDistribution:
    """Time-to-first-token distribution across streaming entries.

    Percentiles are ``None`` when there are too few samples to compute them
    meaningfully (``statistics.quantiles`` requires at least 2 data points;
    we additionally require 4+ samples for the higher percentiles to be more
    than a duplicate of ``max``).
    """

    count: int
    min_ms: int | None = None
    max_ms: int | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None


@dataclass(frozen=True, slots=True)
class StatsSummary:
    """Aggregate stats over a cassette."""

    total: int
    by_provider: dict[str, int] = field(default_factory=_empty_str_int_dict)
    by_status_class: dict[str, int] = field(default_factory=_empty_str_int_dict)
    error_rate: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    ttft: TTFTDistribution = field(default_factory=lambda: TTFTDistribution(count=0))


# ─── Public API ────────────────────────────────────────────────────────


def aggregate(entries: Iterable[CassetteEntry]) -> StatsSummary:
    """Walk ``entries`` once and produce a :class:`StatsSummary`.

    Single-pass: every counter is updated in the same loop, including the
    TTFT samples (kept as a list until the end where percentiles are
    computed). No quadratic work; ``O(n)`` over entries with a final
    ``O(n log n)`` sort inside :func:`statistics.quantiles`.
    """
    total = 0
    by_provider: dict[str, int] = {}
    by_status_class: dict[str, int] = {}
    non_2xx = 0
    input_tokens = 0
    output_tokens = 0
    ttft_samples: list[int] = []

    for entry in entries:
        total += 1
        by_provider[entry.provider] = by_provider.get(entry.provider, 0) + 1

        klass = _status_class(entry.response.status)
        by_status_class[klass] = by_status_class.get(klass, 0) + 1
        if klass != "2xx":
            non_2xx += 1

        inp, out = _extract_tokens(entry)
        input_tokens += inp
        output_tokens += out

        ttft = _ttft_ms(entry)
        if ttft is not None:
            ttft_samples.append(ttft)

    error_rate = (non_2xx / total) if total else 0.0
    return StatsSummary(
        total=total,
        by_provider=by_provider,
        by_status_class=by_status_class,
        error_rate=error_rate,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        ttft=_distribution(ttft_samples),
    )


# ─── Internals ─────────────────────────────────────────────────────────


def _status_class(code: int) -> str:
    """``200`` → ``"2xx"``. Codes outside 100-599 collapse into ``"5xx"``."""
    bucket = code // 100
    if bucket in (2, 3, 4, 5):
        return f"{bucket}xx"
    # Out-of-range codes (0, 1xx, 6xx+) are treated as errors so the
    # error-rate stays honest.
    return "5xx"


def _ttft_ms(entry: CassetteEntry) -> int | None:
    """Return the first chunk's ``t_offset_ms`` for streaming entries; else ``None``.

    Per the cassette schema, ``t_offset_ms`` is "ms since first byte of the
    upstream response," so the first chunk's offset IS the time-to-first-token.
    """
    chunks = entry.response.stream_chunks
    if not chunks:
        return None
    return chunks[0].t_offset_ms


def _distribution(samples: list[int]) -> TTFTDistribution:
    """Compute min/max/p50/p95/p99 over ``samples`` with safe-degrade rules."""
    n = len(samples)
    if n == 0:
        return TTFTDistribution(count=0)

    minimum = min(samples)
    maximum = max(samples)

    # statistics.quantiles needs at least 2 data points. Below 4 samples,
    # higher percentiles are essentially noise — leave them None to signal
    # "not enough data" to the consumer.
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    if n >= 2:
        qs = statistics.quantiles(samples, n=100, method="inclusive")
        # qs is length 99: qs[i] is the (i+1)th percentile.
        p50 = qs[49]
        if n >= 4:
            p95 = qs[94]
            p99 = qs[98]

    return TTFTDistribution(
        count=n,
        min_ms=minimum,
        max_ms=maximum,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
    )


# ─── Token extraction ──────────────────────────────────────────────────


def _extract_tokens(entry: CassetteEntry) -> tuple[int, int]:
    """Return ``(input_tokens, output_tokens)`` for ``entry``; ``(0, 0)`` if none.

    For streaming entries the usage block typically lives on the final chunk;
    for non-streaming entries it lives on the response body. We look at both
    in that order.
    """
    source = _usage_source(entry)
    if not isinstance(source, dict):
        return 0, 0
    return _read_tokens(cast(dict[str, Any], source))


def _usage_source(entry: CassetteEntry) -> Any:
    """Pick the dict most likely to carry the ``usage`` field."""
    chunks = entry.response.stream_chunks
    if chunks:
        return _last_chunk_with_usage(chunks)
    return entry.response.body


def _last_chunk_with_usage(chunks: list[StreamChunk]) -> Any:
    """Return the last chunk's data that carries a usage block (OpenAI streams
    place usage on the penultimate chunk; Anthropic on ``message_delta``)."""
    for chunk in reversed(chunks):
        data = chunk.data
        if isinstance(data, dict):
            d = cast(dict[str, Any], data)
            if "usage" in d or "usageMetadata" in d:
                return d
    # No chunk had usage — fall back to the last parsed JSON chunk so the
    # caller can still try to read it (and get (0, 0) cleanly).
    for chunk in reversed(chunks):
        data = chunk.data
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
    return None


def _read_tokens(d: dict[str, Any]) -> tuple[int, int]:
    """Pull (input, output) tokens from a dict in any of the three known shapes."""
    # Gemini — usageMetadata.{prompt,candidates}TokenCount
    meta = d.get("usageMetadata")
    if isinstance(meta, dict):
        m = cast(dict[str, Any], meta)
        return (
            _as_int(m.get("promptTokenCount")),
            _as_int(m.get("candidatesTokenCount")),
        )

    # OpenAI / Anthropic — usage.{prompt|input}_tokens, usage.{completion|output}_tokens
    usage = d.get("usage")
    if isinstance(usage, dict):
        u = cast(dict[str, Any], usage)
        inp = u.get("prompt_tokens")
        if inp is None:
            inp = u.get("input_tokens")
        out = u.get("completion_tokens")
        if out is None:
            out = u.get("output_tokens")
        return _as_int(inp), _as_int(out)

    return 0, 0


def _as_int(value: Any) -> int:
    """Coerce a numeric-ish value to int; non-numeric / None → 0."""
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
