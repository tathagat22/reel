"""Proxy runtime configuration.

Resolved once at startup. Everything that needs a knob lives here so we don't
sprinkle ``os.environ`` reads through the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Mode = Literal["record", "replay", "auto"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7878

# Upstream defaults — overridable via env or CLI flags.
DEFAULT_OPENAI_UPSTREAM = "https://api.openai.com"


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """Immutable runtime configuration for a single proxy instance."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    mode: Mode = "auto"
    cassette_path: str | None = None
    openai_upstream: str = DEFAULT_OPENAI_UPSTREAM
    request_timeout_seconds: float = 60.0
    replay_timing_multiplier: float = 1.0
    """Pacing for streamed replay chunks. ``1.0`` = realtime (default),
    ``0.0`` = fast (no sleep), ``N`` (>1) = N-times-slower playback."""

    @classmethod
    def from_env(cls) -> ProxyConfig:
        """Build a config purely from env vars. CLI overrides happen on top."""
        return cls(
            host=os.environ.get("REEL_HOST", DEFAULT_HOST),
            port=int(os.environ.get("REEL_PORT", DEFAULT_PORT)),
            mode=_parse_mode(os.environ.get("REEL_MODE", "auto")),
            cassette_path=os.environ.get("REEL_CASSETTE"),
            openai_upstream=os.environ.get("REEL_OPENAI_UPSTREAM", DEFAULT_OPENAI_UPSTREAM),
            request_timeout_seconds=float(os.environ.get("REEL_TIMEOUT", "60")),
            replay_timing_multiplier=float(os.environ.get("REEL_REPLAY_TIMING", "1.0")),
        )


def _parse_mode(raw: str) -> Mode:
    normalized = raw.strip().lower()
    if normalized not in ("record", "replay", "auto"):
        raise ValueError(f"invalid REEL_MODE {raw!r}; expected record|replay|auto")
    return normalized  # type: ignore[return-value]
