"""Upstream routing.

Sprint 1: a single upstream per proxy instance (OpenAI by default). The router's
job is twofold:

1. Decide which upstream a given request path should hit (today: always the
   one configured upstream, but only if the path matches an allowed prefix).
2. Refuse paths that don't look like a known LLM endpoint, so misconfigured
   clients fail loudly with 404 instead of silently proxying garbage upstream.

Multi-provider routing (Anthropic + Gemini) arrives in Sprint 3 alongside the
adapter rewrite. The interface is shaped to absorb that change without breaking
callers.
"""

from __future__ import annotations

from dataclasses import dataclass

from reel.proxy.config import ProxyConfig

# OpenAI client SDKs hit /v1/... by default. We accept both with and without
# the /v1 prefix in case the user sets ``OPENAI_BASE_URL`` directly to our root.
OPENAI_ALLOWED_PREFIXES: tuple[str, ...] = (
    "/v1/",
    "/chat/",
    "/completions",
    "/embeddings",
    "/models",
)


@dataclass(frozen=True, slots=True)
class Upstream:
    """A single upstream destination."""

    provider: str
    base_url: str


class Router:
    """Resolve a proxied request to its upstream destination.

    A return of ``None`` from :py:meth:`resolve` means "no route" — the proxy
    will respond with 404 rather than blind-forwarding.
    """

    def __init__(self, upstream: Upstream, allowed_prefixes: tuple[str, ...]) -> None:
        self._upstream = upstream
        self._allowed = allowed_prefixes

    @property
    def upstream(self) -> Upstream:
        return self._upstream

    @property
    def allowed_prefixes(self) -> tuple[str, ...]:
        return self._allowed

    def resolve(self, path: str) -> Upstream | None:
        for prefix in self._allowed:
            if path.startswith(prefix):
                return self._upstream
        return None

    @classmethod
    def from_config(cls, config: ProxyConfig) -> Router:
        return cls(
            upstream=Upstream(provider="openai", base_url=config.openai_upstream),
            allowed_prefixes=OPENAI_ALLOWED_PREFIXES,
        )
