"""High-level Cassette facade.

A :class:`Cassette` instance owns one on-disk JSONL file and keeps an
in-memory index of its entries so lookups don't re-read the file each time.
Appends are durable (written to disk before the in-memory list is updated) so
crash recovery yields a consistent index on the next load.

If the cassette's first line is a ``{"_meta": {...}}`` envelope, its
``match`` settings are loaded into :py:attr:`match_config` and applied by
:py:meth:`find_smart` automatically.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from reel.adapters.base import ProviderAdapter
from reel.cassette.matcher import MatchConfig, find, find_exact
from reel.cassette.reader import CassetteReader
from reel.cassette.schema import CassetteEntry
from reel.cassette.writer import CassetteWriter


class Cassette:
    """Combined reader + writer with an in-memory entry index."""

    def __init__(self, path: Path | str) -> None:
        self._writer = CassetteWriter(path)
        self._reader = CassetteReader(path)
        self._meta = self._reader.read_meta()
        self._entries: list[CassetteEntry] = self._reader.load_all()
        self._index_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._writer.path

    @property
    def match_config(self) -> MatchConfig:
        """Match settings — from the cassette's ``_meta`` line if set, else defaults."""
        if self._meta is None or self._meta.match is None:
            return MatchConfig()
        m = self._meta.match
        return MatchConfig(
            mode=m.mode,
            ignore_fields=tuple(m.ignore_fields),
            fuzzy_threshold=m.fuzzy_threshold,
        )

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[CassetteEntry]:
        return list(self._entries)

    def find(self, fingerprint: str) -> CassetteEntry | None:
        """Exact-fingerprint match against the in-memory index. Sprint 1 API."""
        return find_exact(self._entries, fingerprint)

    def find_smart(
        self,
        *,
        body: bytes,
        path: str,
        adapter: ProviderAdapter,
    ) -> CassetteEntry | None:
        """Look up using the cassette's persisted match config (Sprint 3.5)."""
        return find(self._entries, body=body, path=path, adapter=adapter, config=self.match_config)

    async def append(self, entry: CassetteEntry) -> None:
        """Append durably to disk then mirror into the in-memory index."""
        await self._writer.append(entry)
        async with self._index_lock:
            self._entries.append(entry)
