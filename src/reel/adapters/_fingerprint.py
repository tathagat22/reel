"""Shared fingerprint algorithm.

Every provider hashes the same way: canonicalize the JSON body, drop the
provider-specific "irrelevant" keys, prepend the endpoint, hash. Each adapter
contributes only the ignore set — that's enough to honor the difference
between, say, OpenAI's ``safety_identifier`` and Anthropic's ``metadata``
without duplicating the canonicalization machinery.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

# Tag included before hashing so the algorithm version is part of the namespace.
# Bumping this invalidates all old fingerprints, which is desirable on
# breaking changes (e.g., changing the canonicalization rule).
ALGORITHM_VERSION = "v1"


def compute_fingerprint(
    body: bytes,
    *,
    endpoint: str,
    ignore_keys: frozenset[str],
) -> str:
    """Stable ``"sha256:<hex>"`` fingerprint for a JSON-body request.

    Args:
        body: Raw request body. Non-JSON bodies hash to a raw-bytes-prefixed
            sentinel instead.
        endpoint: Request path (or any string the caller wants in the seed).
            Different endpoints with identical bodies produce different hashes.
        ignore_keys: Top-level and nested keys that don't affect generated
            content. Examples: ``stream``, ``user``, ``metadata``.
    """
    payload = _canonicalize(body, ignore_keys=ignore_keys)
    seed = f"{ALGORITHM_VERSION}\n{endpoint}\n{payload}".encode()
    return "sha256:" + hashlib.sha256(seed).hexdigest()


def _canonicalize(body: bytes, *, ignore_keys: frozenset[str]) -> str:
    if not body:
        return ""
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError:
        return "raw:" + hashlib.sha256(body).hexdigest()

    cleaned = _drop_ignored(parsed, ignore_keys)
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _drop_ignored(value: Any, ignore_keys: frozenset[str]) -> Any:
    """Recursively drop ignored keys from dicts. List order preserved."""
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        return {k: _drop_ignored(v, ignore_keys) for k, v in d.items() if k not in ignore_keys}
    if isinstance(value, list):
        lst = cast(list[Any], value)
        return [_drop_ignored(item, ignore_keys) for item in lst]
    return value
