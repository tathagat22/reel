"""OpenAI provider adapter.

Implements :class:`reel.adapters.base.ProviderAdapter` for the OpenAI HTTP API.

## Fingerprint contract

* **Identical for semantically-equivalent requests.** Whitespace and key order
  do not affect the hash.
* **Different for any change to generation inputs.** Model, messages, tools,
  temperature, top_p, etc. all participate.
* **Stable across SDK versions.** We hash a curated normalization, not the
  exact wire body, so SDK formatting drift doesn't break replays.
* **Includes the endpoint path.** ``/v1/chat/completions`` and
  ``/v1/completions`` produce different hashes even with identical bodies.

Fields that are *excluded* describe how the response is delivered or
observed, not what the response will contain:

* ``stream`` / ``stream_options`` — delivery transport
* ``user`` / ``safety_identifier`` — caller tagging
* ``metadata`` — logging only
* ``store`` — server-side persistence flag
* ``service_tier`` — routing hint
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

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

# Tag included before hashing so the algorithm version is part of the namespace.
# Bumping this invalidates all old fingerprints, which is desirable on
# breaking changes (e.g., changing which fields are ignored).
ALGORITHM_VERSION = "v1"

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
    """Compute a stable sha256 fingerprint for an OpenAI request.

    Args:
        body: Raw request body bytes (typically a JSON-encoded chat completion).
        endpoint: Request path (e.g., ``"/v1/chat/completions"``). Included in
            the hash so different endpoints with identical bodies don't collide.

    Returns:
        ``"sha256:<64 hex chars>"``. The ``sha256:`` prefix is part of the
        contract so future algorithm migrations stay unambiguous.
    """
    payload = _canonicalize(body)
    seed = f"{ALGORITHM_VERSION}\n{endpoint}\n{payload}".encode()
    return "sha256:" + hashlib.sha256(seed).hexdigest()


def _canonicalize(body: bytes) -> str:
    """Return a canonical string form of the request body for hashing."""
    if not body:
        return ""
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError:
        # Non-JSON body: hash the raw bytes verbatim. (No OpenAI endpoint in
        # use today is non-JSON, but multipart uploads will land in future
        # sprints and we want a defined behavior.)
        return "raw:" + hashlib.sha256(body).hexdigest()

    cleaned = _drop_ignored(parsed)
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _drop_ignored(value: Any) -> Any:
    """Recursively drop fingerprint-irrelevant keys from dicts (lists kept in order)."""
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        return {k: _drop_ignored(v) for k, v in d.items() if k not in FINGERPRINT_IGNORE}
    if isinstance(value, list):
        lst = cast(list[Any], value)
        return [_drop_ignored(item) for item in lst]
    return value


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


# Module-level singleton — adapters are stateless, so one instance is enough.
adapter: ProviderAdapter = OpenAIAdapter()
