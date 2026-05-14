"""High-level Cassette facade.

A :class:`Cassette` instance owns one on-disk JSONL file and keeps an
in-memory index of its entries so lookups don't re-read the file each time.
Appends are durable (written to disk before the in-memory list is updated) so
crash recovery yields a consistent index on the next load.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from reel.cassette.matcher import find_exact
from reel.cassette.reader import CassetteReader
from reel.cassette.schema import CassetteEntry
from reel.cassette.writer import CassetteWriter


class Cassette:
    """Combined reader + writer with an in-memory entry index."""

    def __init__(self, path: Path | str) -> None:
        self._writer = CassetteWriter(path)
        self._reader = CassetteReader(path)
        self._entries: list[CassetteEntry] = self._reader.load_all()
        self._index_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._writer.path

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[CassetteEntry]:
        return list(self._entries)

    def find(self, fingerprint: str) -> CassetteEntry | None:
        """Exact-fingerprint match against the in-memory index."""
        return find_exact(self._entries, fingerprint)

    async def append(self, entry: CassetteEntry) -> None:
        """Append durably to disk then mirror into the in-memory index."""
        await self._writer.append(entry)
        async with self._index_lock:
            self._entries.append(entry)
