"""Exact-fingerprint cassette matching.

Sprint 1 supports only exact matching. The smart matchers (normalized,
ignore-fields, fuzzy) arrive in Sprint 3 alongside the multi-provider adapter
refactor.
"""

from __future__ import annotations

from collections.abc import Sequence

from reel.cassette.schema import CassetteEntry


def find_exact(entries: Sequence[CassetteEntry], fingerprint: str) -> CassetteEntry | None:
    """Return the *most recent* entry matching this fingerprint, or ``None``.

    Most-recent semantics let callers re-record a request and have replays
    pick up the new response without having to truncate the cassette.
    """
    for entry in reversed(entries):
        if entry.request.fingerprint == fingerprint:
            return entry
    return None
