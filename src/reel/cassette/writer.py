"""Append-only JSONL cassette writer.

Threading model: file appends are serialized with an :class:`asyncio.Lock` and
the actual ``write`` runs on a worker thread via :func:`asyncio.to_thread` so
the event loop stays unblocked under concurrent record traffic.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from reel.cassette.schema import CassetteEntry


def generate_id() -> str:
    """Short, unique-enough request ID (millisecond + 8 hex chars of entropy)."""
    return f"req_{int(time.time() * 1000):013d}_{secrets.token_hex(4)}"


def now_iso() -> str:
    """ISO 8601 UTC string with seconds precision (``YYYY-MM-DDTHH:MM:SS+00:00``)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class CassetteWriter:
    """Append-only JSONL writer."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    async def append(self, entry: CassetteEntry) -> None:
        """Append one entry as a single JSONL line. Concurrency-safe."""
        line = entry.model_dump_json() + "\n"
        async with self._lock:
            await asyncio.to_thread(self._write_line, line)

    def _write_line(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
