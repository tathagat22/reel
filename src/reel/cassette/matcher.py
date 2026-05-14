"""Cassette matchers.

Four modes:

* ``exact`` — sha256 over the raw request bytes (no normalization).
* ``normalized`` — adapter fingerprint (sort keys, drop adapter-default
  ignored fields). The default and what every Sprint 1-2 cassette uses.
* ``ignore-fields`` — like ``normalized`` but additionally drops the
  user-supplied keys. Useful when a request includes a per-call
  ``request_id`` / ``trace_id`` you don't want in the hash.
* ``fuzzy`` — embedding-similarity over the prompt text. Requires the
  optional ``reel[fuzzy]`` dependency (``sentence-transformers``).

The default behavior preserves Sprint 1 semantics: bare :func:`find_exact`
still does fingerprint lookup.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from reel.adapters._fingerprint import compute_fingerprint
from reel.adapters.base import ProviderAdapter
from reel.cassette.body import serialize_from_storage
from reel.cassette.schema import CassetteEntry

MatchMode = Literal["exact", "normalized", "ignore-fields", "fuzzy"]


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """How a Matcher should compare incoming requests to cassette entries."""

    mode: MatchMode = "normalized"
    ignore_fields: tuple[str, ...] = field(default_factory=tuple)
    """Extra keys to drop in ``ignore-fields`` mode (added to adapter defaults)."""
    fuzzy_threshold: float = 0.85
    """Cosine-similarity threshold in ``fuzzy`` mode (0.0 - 1.0)."""


# ─── Public API ────────────────────────────────────────────────────────


def find_exact(entries: Sequence[CassetteEntry], fingerprint: str) -> CassetteEntry | None:
    """Most-recent-wins fingerprint match. Sprint 1 API preserved."""
    for entry in reversed(entries):
        if entry.request.fingerprint == fingerprint:
            return entry
    return None


def find(
    entries: Sequence[CassetteEntry],
    *,
    body: bytes,
    path: str,
    adapter: ProviderAdapter,
    config: MatchConfig = MatchConfig(),  # noqa: B008 — frozen dataclass; safe default
) -> CassetteEntry | None:
    """Configurable matcher entry point."""
    if config.mode == "normalized":
        return find_exact(entries, adapter.fingerprint(body, endpoint=path))
    if config.mode == "exact":
        return _find_byte_exact(entries, body, path)
    if config.mode == "ignore-fields":
        return _find_with_extra_ignore(entries, body, path, adapter, config.ignore_fields)
    if config.mode == "fuzzy":
        return _find_fuzzy(entries, body, path, config.fuzzy_threshold)
    # Unreachable — MatchMode is a Literal type
    raise ValueError(f"unknown match mode: {config.mode!r}")


# ─── Mode implementations ──────────────────────────────────────────────


def _find_byte_exact(
    entries: Sequence[CassetteEntry],
    body: bytes,
    path: str,
) -> CassetteEntry | None:
    """sha256 over raw bytes — no JSON parsing, no normalization."""
    target_hash = hashlib.sha256(body).hexdigest()
    for entry in reversed(entries):
        if entry.request.path != path:
            continue
        stored_body = serialize_from_storage(entry.request.body)
        if hashlib.sha256(stored_body).hexdigest() == target_hash:
            return entry
    return None


def _find_with_extra_ignore(
    entries: Sequence[CassetteEntry],
    body: bytes,
    path: str,
    adapter: ProviderAdapter,
    extra_ignore: tuple[str, ...],
) -> CassetteEntry | None:
    """Recompute fingerprints with adapter ignore set plus user-supplied keys."""
    full_ignore = adapter.fingerprint_ignore | frozenset(extra_ignore)
    target = compute_fingerprint(body, endpoint=path, ignore_keys=full_ignore)
    for entry in reversed(entries):
        stored_body = serialize_from_storage(entry.request.body)
        entry_fp = compute_fingerprint(
            stored_body, endpoint=entry.request.path, ignore_keys=full_ignore
        )
        if entry_fp == target:
            return entry
    return None


def _find_fuzzy(
    entries: Sequence[CassetteEntry],
    body: bytes,
    path: str,
    threshold: float,
) -> CassetteEntry | None:
    """Embedding-similarity lookup.

    Lazy import of ``sentence-transformers`` so the dependency is truly
    optional. The model is cached at module scope after first use.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "fuzzy match mode requires the optional 'reel[fuzzy]' install. "
            "Run: uv pip install 'reel[fuzzy]'"
        ) from exc

    incoming_text = _extract_text(body)
    if not incoming_text:
        return None

    model = _get_embedding_model(SentenceTransformer)
    incoming_emb = model.encode([incoming_text], convert_to_numpy=True)[0]

    best_entry: CassetteEntry | None = None
    best_score = -1.0
    for entry in reversed(entries):
        if entry.request.path != path:
            continue
        entry_text = _extract_text(serialize_from_storage(entry.request.body))
        if not entry_text:
            continue
        entry_emb = model.encode([entry_text], convert_to_numpy=True)[0]
        score = _cosine(incoming_emb, entry_emb)
        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry if best_score >= threshold else None


# ─── Helpers ───────────────────────────────────────────────────────────

_embedding_model_cache: Any = None


def _get_embedding_model(model_cls: Any) -> Any:
    global _embedding_model_cache
    if _embedding_model_cache is None:
        # Small, fast, ~80MB — good enough for prompt similarity.
        _embedding_model_cache = model_cls("sentence-transformers/all-MiniLM-L6-v2")
    return _embedding_model_cache


def _extract_text(body: bytes) -> str:
    """Pull human-readable prompt text out of a request body for fuzzy matching."""
    if not body:
        return ""
    try:
        parsed: Any = json.loads(body)
    except json.JSONDecodeError:
        return body.decode("utf-8", errors="replace")

    if not isinstance(parsed, dict):
        return json.dumps(parsed)

    p = cast(dict[str, Any], parsed)
    # OpenAI / Anthropic: messages = [{role, content}]
    if "messages" in p:
        return _flatten_messages(p.get("messages", []))
    # Anthropic separately can have a top-level "system"
    if "system" in p and isinstance(p["system"], str):
        return p["system"]
    # Gemini: contents = [{role, parts: [{text}]}]
    if "contents" in p:
        return _flatten_gemini_contents(p.get("contents", []))
    # Embeddings — input string or list of strings
    if "input" in p:
        inp = p["input"]
        if isinstance(inp, str):
            return inp
        if isinstance(inp, list):
            return " ".join(str(s) for s in cast(list[Any], inp))
    return json.dumps(p)


def _flatten_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for m in cast(list[Any], messages):
        if isinstance(m, dict):
            md = cast(dict[str, Any], m)
            content = md.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for c in cast(list[Any], content):
                    if isinstance(c, dict):
                        cd = cast(dict[str, Any], c)
                        if "text" in cd:
                            parts.append(str(cd["text"]))
    return " ".join(parts)


def _flatten_gemini_contents(contents: Any) -> str:
    if not isinstance(contents, list):
        return ""
    out: list[str] = []
    for entry in cast(list[Any], contents):
        if isinstance(entry, dict):
            ed = cast(dict[str, Any], entry)
            parts_raw = ed.get("parts", [])
            if isinstance(parts_raw, list):
                for p in cast(list[Any], parts_raw):
                    if isinstance(p, dict):
                        pd = cast(dict[str, Any], p)
                        if "text" in pd:
                            out.append(str(pd["text"]))
    return " ".join(out)


def _cosine(a: Any, b: Any) -> float:
    """Cosine similarity between two 1-D numpy vectors (lazy-typed to keep numpy optional)."""
    import math

    dot = float(sum(float(x) * float(y) for x, y in zip(a, b, strict=False)))
    na = math.sqrt(float(sum(float(x) * float(x) for x in a)))
    nb = math.sqrt(float(sum(float(y) * float(y) for y in b)))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
