"""Gemini provider adapter.

Gemini's HTTP API lives under ``/v1beta/models/<model>:<verb>`` where
``<verb>`` is one of ``generateContent`` (buffered) or
``streamGenerateContent`` (SSE). Unlike OpenAI / Anthropic, streaming is
signaled by the URL **verb**, not a ``"stream": true`` body field — so this
adapter overrides :py:meth:`ProviderAdapter.is_streaming` accordingly.

No fingerprint ignore set is needed: Gemini bodies contain only generation
inputs, and the streaming-vs-buffered distinction is encoded in the path
(which is already part of the fingerprint seed).
"""

from __future__ import annotations

from reel.adapters._fingerprint import compute_fingerprint
from reel.adapters.base import ProviderAdapter

FINGERPRINT_IGNORE: frozenset[str] = frozenset()

GEMINI_PATH_PREFIXES: tuple[str, ...] = (
    "/v1beta/models/",
    "/v1beta/",
)

# Sentinel substring marking a streaming endpoint in the URL.
STREAM_VERB = ":streamGenerateContent"


def fingerprint(body: bytes, *, endpoint: str = "") -> str:
    return compute_fingerprint(body, endpoint=endpoint, ignore_keys=FINGERPRINT_IGNORE)


class GeminiAdapter(ProviderAdapter):
    """Gemini provider implementation of :class:`ProviderAdapter`."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def path_prefixes(self) -> tuple[str, ...]:
        return GEMINI_PATH_PREFIXES

    def fingerprint(self, body: bytes, *, endpoint: str) -> str:
        return fingerprint(body, endpoint=endpoint)

    def is_streaming(self, path: str, body: bytes) -> bool:
        # Gemini signals streaming via the URL verb, ignoring the body.
        _ = body
        return STREAM_VERB in path


adapter: ProviderAdapter = GeminiAdapter()
