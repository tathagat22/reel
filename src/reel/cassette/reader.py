"""JSONL cassette reader.

Loads entries lazily (iterator) or eagerly (``load_all``). Tolerates blank
lines and trailing whitespace but treats malformed lines as fatal — silently
skipping corrupt entries would mask cassette drift, which is worse than a loud
test failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from reel.cassette.schema import CassetteEntry


class CassetteReader:
    """Read entries from an on-disk JSONL cassette."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def iter_entries(self) -> Iterator[CassetteEntry]:
        """Yield entries one at a time. Empty file → empty iterator."""
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                yield CassetteEntry.model_validate_json(line)

    def load_all(self) -> list[CassetteEntry]:
        """Load every entry into memory. Returns ``[]`` for missing files."""
        return list(self.iter_entries())
