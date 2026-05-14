"""Incremental Server-Sent Events parser.

Per the WHATWG spec (https://html.spec.whatwg.org/multipage/server-sent-events.html),
an SSE event is a sequence of ``field: value`` lines terminated by a blank line.

The parser is byte-oriented and incremental — feed it whatever the transport
hands you and it will yield :class:`SSEEvent` objects as soon as it has a
complete one. The remaining buffered bytes are kept across calls so events
split across TCP packets parse correctly.

Sprint 2.1 supports the OpenAI flavor: only ``data:`` lines, terminated by a
blank line, with a ``[DONE]`` sentinel as the final event. Anthropic's
``event: <name>\\ndata: {...}`` shape also parses correctly because the parser
captures ``event``, ``id``, and ``retry`` fields per the spec — the Anthropic
adapter just consumes those fields when it lands in Sprint 3.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """One parsed Server-Sent Event."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None


class SSEParser:
    """Incremental parser. Construct, ``feed(bytes)`` repeatedly, ``close()`` at end."""

    def __init__(self) -> None:
        self._buffer = b""
        self._data_lines: list[str] = []
        self._event_type: str | None = None
        self._event_id: str | None = None
        self._retry: int | None = None

    def feed(self, chunk: bytes) -> Iterator[SSEEvent]:
        """Append bytes; yield every event that becomes complete."""
        self._buffer += chunk
        while True:
            newline_idx = self._buffer.find(b"\n")
            if newline_idx == -1:
                break
            raw_line = self._buffer[:newline_idx]
            self._buffer = self._buffer[newline_idx + 1 :]
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            event = self._process_line(raw_line.decode("utf-8"))
            if event is not None:
                yield event

    def close(self) -> Iterator[SSEEvent]:
        """Flush any remaining in-progress event when the stream ends."""
        # A line without a trailing newline is still a valid SSE line.
        if self._buffer:
            tail = self._buffer.decode("utf-8")
            if tail.endswith("\r"):
                tail = tail[:-1]
            self._buffer = b""
            event = self._process_line(tail)
            if event is not None:
                yield event
        # And the in-progress event (no terminating blank line — graceful close).
        flushed = self._flush()
        if flushed is not None:
            yield flushed

    def _process_line(self, line: str) -> SSEEvent | None:
        if line == "":
            return self._flush()
        if line.startswith(":"):
            return None  # comment per spec
        if ":" in line:
            field, _, value = line.partition(":")
            # Spec says: strip a single leading space from the value if present.
            if value.startswith(" "):
                value = value[1:]
        else:
            field = line
            value = ""

        if field == "data":
            self._data_lines.append(value)
        elif field == "event":
            self._event_type = value
        elif field == "id":
            self._event_id = value
        elif field == "retry":
            # Spec says ignore non-integer retry values.
            with contextlib.suppress(ValueError):
                self._retry = int(value)

        return None

    def _flush(self) -> SSEEvent | None:
        if not self._data_lines:
            self._reset()
            return None
        event = SSEEvent(
            data="\n".join(self._data_lines),
            event=self._event_type,
            id=self._event_id,
            retry=self._retry,
        )
        self._reset()
        return event

    def _reset(self) -> None:
        self._data_lines = []
        self._event_type = None
        self._event_id = None
        self._retry = None
