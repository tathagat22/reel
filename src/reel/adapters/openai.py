"""OpenAI provider adapter.

Implements :class:`reel.adapters.base.ProviderAdapter` for the OpenAI HTTP API.

Fields excluded from the fingerprint describe how the response is delivered
or observed, not what the response will contain:

* ``stream`` / ``stream_options`` — delivery transport
* ``user`` / ``safety_identifier`` — caller tagging
* ``metadata`` — logging only
* ``store`` — server-side persistence flag
* ``service_tier`` — routing hint
"""

from __future__ import annotations

from reel.adapters._fingerprint import compute_fingerprint
from reel.adapters.base import ProviderAdapter

FINGERPRINT_IGNORE: frozenset[str] = frozenset(
    {
        "stream",
        "stream_options",
        "user",
        "safety_identifier",
        "metadata",
        "store",
        "service_tier",
    }
)

# URL prefixes the OpenAI API responds to. Two forms supported:
# - Canonical ``/v1/...`` (when ``OPENAI_BASE_URL=http://proxy:7878``).
# - SDK-managed ``/v1`` already in the base URL, e.g. user sets
#   ``OPENAI_BASE_URL=http://proxy:7878/v1`` and the SDK hits ``/chat/...``.
OPENAI_PATH_PREFIXES: tuple[str, ...] = (
    "/v1/chat/",
    "/v1/completions",
    "/v1/embeddings",
    "/v1/models",
    "/v1/audio",
    "/v1/images",
    "/v1/moderations",
    "/v1/batches",
    "/v1/files",
    "/v1/responses",
    "/chat/",
    "/completions",
    "/embeddings",
    "/models",
)


def fingerprint(body: bytes, *, endpoint: str = "") -> str:
    """Convenience function — equivalent to ``OpenAIAdapter().fingerprint(...)``."""
    return compute_fingerprint(body, endpoint=endpoint, ignore_keys=FINGERPRINT_IGNORE)


class OpenAIAdapter(ProviderAdapter):
    """OpenAI provider implementation of :class:`ProviderAdapter`."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def path_prefixes(self) -> tuple[str, ...]:
        return OPENAI_PATH_PREFIXES

    def fingerprint(self, body: bytes, *, endpoint: str) -> str:
        return fingerprint(body, endpoint=endpoint)

    @property
    def fingerprint_ignore(self) -> frozenset[str]:
        return FINGERPRINT_IGNORE


# Module-level singleton — adapters are stateless, so one instance is enough.
adapter: ProviderAdapter = OpenAIAdapter()
