"""JSONL cassette reader.

Loads entries lazily (iterator) or eagerly (``load_all``). The first line of
a cassette MAY be a ``{"_meta": {...}}`` envelope carrying file-wide settings
(currently just match config). Meta lines are skipped during entry iteration
and exposed separately via :py:meth:`CassetteReader.read_meta`.

Tolerates blank lines and trailing whitespace but treats malformed lines as
fatal — silently skipping corrupt entries would mask cassette drift, which is
worse than a loud test failure.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from reel.cassette.schema import CassetteEntry, CassetteMeta

META_KEY = "_meta"


class CassetteReader:
    """Read entries from an on-disk JSONL cassette."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def read_meta(self) -> CassetteMeta | None:
        """Return the cassette's ``_meta`` envelope, or ``None`` if absent.

        Only the first non-blank line is inspected — meta must be at the top
        of the file (otherwise it's just stored data).
        """
        if not self._path.exists():
            return None
        with self._path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                data: Any = json.loads(line)
                if isinstance(data, dict) and META_KEY in cast(dict[str, Any], data):
                    meta = cast(dict[str, Any], data)[META_KEY]
                    return CassetteMeta.model_validate(meta)
                return None
        return None

    def iter_entries(self) -> Iterator[CassetteEntry]:
        """Yield entries one at a time. Empty file → empty iterator. Skips meta line."""
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                data: Any = json.loads(line)
                if isinstance(data, dict) and META_KEY in cast(dict[str, Any], data):
                    continue  # meta envelope — not an entry
                yield CassetteEntry.model_validate(data)

    def load_all(self) -> list[CassetteEntry]:
        """Load every entry into memory. Returns ``[]`` for missing files."""
        return list(self.iter_entries())
