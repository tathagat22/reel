"""Provider adapter interface.

Each LLM provider (OpenAI, Anthropic, Gemini, ...) plugs into Reel via a
:class:`ProviderAdapter`. The adapter contributes three things:

1. A short, stable :py:attr:`name` used as the ``provider`` field on cassette
   entries — letting humans (and ``reel inspect``) tell at a glance which API
   a recorded call came from.
2. The set of URL :py:attr:`path_prefixes` the provider responds to. The
   proxy router uses these to dispatch incoming requests to the right
   upstream without the user having to specify a provider on the command
   line.
3. A :py:meth:`fingerprint` algorithm that turns a request body into a stable
   hash. Two semantically-equivalent requests must hash the same; any change
   to generation inputs must produce a different hash. The hash is the key
   for cassette lookup.

Sprint 3.1 ships the interface and refactors OpenAI onto it. Anthropic and
Gemini follow in 3.2 / 3.3.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, cast


class ProviderAdapter(ABC):
    """One concrete adapter per supported provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier — ``"openai"``, ``"anthropic"``, ``"gemini"``."""

    @property
    @abstractmethod
    def path_prefixes(self) -> tuple[str, ...]:
        """URL path prefixes this provider's API lives under.

        Multiple entries allow adapters to support both the canonical
        upstream layout (``/v1/...``) and the SDK's "base URL with prefix"
        convention (``/chat/completions`` when the user sets
        ``OPENAI_BASE_URL=http://localhost:7878/v1``).
        """

    @abstractmethod
    def fingerprint(self, body: bytes, *, endpoint: str) -> str:
        """Stable fingerprint of a request body for cassette lookup.

        Must be deterministic, insensitive to cosmetic differences
        (whitespace, key order), sensitive to any change in generation
        inputs, and prefixed with the algorithm namespace (``sha256:``)
        so future migrations are unambiguous.
        """

    @property
    def fingerprint_ignore(self) -> frozenset[str]:
        """Keys this adapter drops from the fingerprint by default.

        Exposed so the ``ignore-fields`` matcher mode can extend the default
        set with user-supplied keys. Default: empty (Gemini-style).
        """
        return frozenset()

    def is_streaming(self, path: str, body: bytes) -> bool:
        """``True`` if this (path, body) describes a streaming request.

        Default implementation: looks for ``"stream": true`` in a top-level
        JSON object. Override for providers that signal streaming differently
        — e.g., Gemini uses ``:streamGenerateContent`` in the URL.
        """
        _ = path  # default ignores the path
        if not body:
            return False
        try:
            parsed: Any = json.loads(body)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        return cast(dict[str, Any], parsed).get("stream") is True
