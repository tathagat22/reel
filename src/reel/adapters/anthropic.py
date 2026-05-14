"""Anthropic provider adapter.

Anthropic's HTTP API lives under ``/v1/messages*``. ``/v1/models`` exists too
but conflicts with OpenAI's ``/v1/models`` — explicit ``/anthropic/`` URL
prefix routing (Sprint 3.2 router) is the way to disambiguate that case.

Ignored fingerprint keys are minimal — only the wire-protocol fields that
don't change generated content:

* ``stream`` — delivery transport
* ``metadata`` — logging only
"""

from __future__ import annotations

from reel.adapters._fingerprint import compute_fingerprint
from reel.adapters.base import ProviderAdapter

FINGERPRINT_IGNORE: frozenset[str] = frozenset(
    {
        "stream",
        "metadata",
    }
)

# Path prefixes for Anthropic. ``/v1/models`` is intentionally omitted to
# avoid colliding with OpenAI; users hitting Anthropic's models endpoint
# should use the explicit ``/anthropic/v1/models`` URL prefix.
ANTHROPIC_PATH_PREFIXES: tuple[str, ...] = (
    "/v1/messages",
    "/v1/complete",
)


def fingerprint(body: bytes, *, endpoint: str = "") -> str:
    return compute_fingerprint(body, endpoint=endpoint, ignore_keys=FINGERPRINT_IGNORE)


class AnthropicAdapter(ProviderAdapter):
    """Anthropic provider implementation of :class:`ProviderAdapter`."""

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def path_prefixes(self) -> tuple[str, ...]:
        return ANTHROPIC_PATH_PREFIXES

    def fingerprint(self, body: bytes, *, endpoint: str) -> str:
        return fingerprint(body, endpoint=endpoint)


adapter: ProviderAdapter = AnthropicAdapter()
