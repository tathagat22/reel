"""Cassette-vs-cassette diff primitives.

Pure functions for comparing two cassettes. The CLI layer owns rendering;
this module just computes alignments and per-entry diffs.

Alignment is O(N+M): we bucket the right-hand entries by ``request.fingerprint``
into a dict, then walk the left side once. Fingerprint collisions on the right
side are handled FIFO so re-recorded duplicate calls still line up in order.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from reel.cassette.schema import CassetteEntry

AlignmentKind = Literal["both", "left_only", "right_only", "changed"]


@dataclass(frozen=True, slots=True)
class Alignment:
    """One paired (or unpaired) row across two cassettes.

    ``kind`` summarizes the pairing:

    * ``"both"`` — fingerprint matched and response bodies are equal.
    * ``"changed"`` — fingerprint matched but the response differs.
    * ``"left_only"`` — entry exists on the left, no counterpart on the right.
    * ``"right_only"`` — entry exists on the right, no counterpart on the left.
    """

    left: CassetteEntry | None
    right: CassetteEntry | None
    kind: AlignmentKind


@dataclass(frozen=True, slots=True)
class EntryDiff:
    """Field-level diff of two paired entries."""

    status_changed: bool
    model_changed: bool
    body_changed: bool
    tokens_delta: int | None
    """``output_tokens_right - output_tokens_left`` when both sides report usage,
    else ``None``."""
    lines: list[str] = field(default_factory=lambda: [])
    """Short human-readable bullets summarizing each detected change."""


def align_entries(a: list[CassetteEntry], b: list[CassetteEntry]) -> list[Alignment]:
    """Pair entries from ``a`` and ``b`` by ``request.fingerprint``.

    Strategy (single-pass, O(N+M)):

    1. Bucket the right side into a ``dict[fingerprint, deque[CassetteEntry]]``.
    2. Walk the left side; for each entry, pop the first right-side entry with
       a matching fingerprint to form a pair. No match → ``left_only``.
    3. Any right-side entries left over after the left walk are emitted as
       ``right_only``, in their original order.

    Pairings classify as ``"both"`` when the response bodies are byte-equal
    after Pydantic round-trip, or ``"changed"`` otherwise.
    """
    right_buckets: dict[str, deque[CassetteEntry]] = defaultdict(deque)
    for entry in b:
        right_buckets[entry.request.fingerprint].append(entry)

    out: list[Alignment] = []
    for left in a:
        bucket = right_buckets.get(left.request.fingerprint)
        if bucket:
            right = bucket.popleft()
            kind: AlignmentKind = "both" if _responses_equal(left, right) else "changed"
            out.append(Alignment(left=left, right=right, kind=kind))
        else:
            out.append(Alignment(left=left, right=None, kind="left_only"))

    # Any right-side entries not consumed by the left walk are right-only.
    # Preserve original right-side order across all buckets.
    leftover_ids: set[int] = set()
    for bucket in right_buckets.values():
        for entry in bucket:
            leftover_ids.add(id(entry))
    if leftover_ids:
        for entry in b:
            if id(entry) in leftover_ids:
                out.append(Alignment(left=None, right=entry, kind="right_only"))

    return out


def compare_entries(left: CassetteEntry, right: CassetteEntry) -> EntryDiff:
    """Field-level diff of a paired left/right entry.

    Computes ``status_changed`` / ``model_changed`` / ``body_changed`` plus a
    token delta (when both sides report usage) and a list of short, printable
    summary lines.
    """
    left_model = _model_name(left)
    right_model = _model_name(right)
    model_changed = left_model != right_model

    status_changed = left.response.status != right.response.status
    body_changed = not _responses_equal(left, right)

    left_out = _output_tokens(left)
    right_out = _output_tokens(right)
    tokens_delta: int | None = (
        right_out - left_out if left_out is not None and right_out is not None else None
    )

    lines: list[str] = []
    if status_changed:
        lines.append(f"status: {left.response.status} → {right.response.status}")
    if model_changed:
        lines.append(f"model: {left_model or '-'} → {right_model or '-'}")
    if body_changed:
        lines.append("response body differs")
    if tokens_delta is not None and tokens_delta != 0:
        sign = "+" if tokens_delta > 0 else ""
        lines.append(f"output tokens: {sign}{tokens_delta}")

    return EntryDiff(
        status_changed=status_changed,
        model_changed=model_changed,
        body_changed=body_changed,
        tokens_delta=tokens_delta,
        lines=lines,
    )


# ─── Helpers ───────────────────────────────────────────────────────────


def _responses_equal(left: CassetteEntry, right: CassetteEntry) -> bool:
    """Byte-equal check on the parsed response (status + body + chunks)."""
    return left.response.model_dump() == right.response.model_dump()


def _model_name(entry: CassetteEntry) -> str | None:
    body = entry.request.body
    if isinstance(body, dict):
        model = cast(dict[str, Any], body).get("model")
        if isinstance(model, str):
            return model
    return None


def _output_tokens(entry: CassetteEntry) -> int | None:
    """Pull output/completion token count from response usage if present.

    OpenAI uses ``completion_tokens``; Anthropic uses ``output_tokens``. Either
    shape works.
    """
    body = entry.response.body
    if not isinstance(body, dict):
        return None
    usage = cast(dict[str, Any], body).get("usage")
    if not isinstance(usage, dict):
        return None
    u = cast(dict[str, Any], usage)
    value = u.get("completion_tokens", u.get("output_tokens"))
    return value if isinstance(value, int) else None
