"""Multi-provider routing.

Two routing styles are supported, in priority order:

1. **Explicit provider URL prefix.** ``/<provider>/<rest>`` strips the prefix
   and routes to ``<provider>``'s upstream. The user sets, e.g.,
   ``ANTHROPIC_BASE_URL=http://localhost:7878/anthropic`` and any path under
   that segment lands on Anthropic. This is the unambiguous form and the
   only way to disambiguate endpoints that several providers share
   (e.g., ``/v1/models``).

2. **Path-prefix matching.** Each adapter declares the URL prefixes it
   responds to. The router scans upstreams in registration order and routes
   to the first match. This preserves the Sprint 1 behavior of pointing
   ``OPENAI_BASE_URL=http://localhost:7878/v1`` at the proxy with no extra
   path segment.
"""

from __future__ import annotations

from dataclasses import dataclass

from reel.adapters.anthropic import adapter as anthropic_adapter
from reel.adapters.base import ProviderAdapter
from reel.adapters.gemini import adapter as gemini_adapter
from reel.adapters.openai import adapter as openai_adapter
from reel.proxy.config import ProxyConfig


@dataclass(frozen=True, slots=True)
class Upstream:
    """A single upstream destination with its adapter."""

    provider: str
    base_url: str
    adapter: ProviderAdapter


@dataclass(frozen=True, slots=True)
class Resolution:
    """The result of a successful routing decision."""

    upstream: Upstream
    rewritten_path: str
    """The path to forward upstream — with any ``/<provider>/`` prefix stripped."""


class Router:
    """Resolve a proxied request to its upstream destination."""

    def __init__(self, upstreams: list[Upstream]) -> None:
        self._upstreams = tuple(upstreams)

    @property
    def upstreams(self) -> tuple[Upstream, ...]:
        return self._upstreams

    @property
    def allowed_prefixes(self) -> tuple[str, ...]:
        """Diagnostic — flat list of every accepted path prefix across providers."""
        accepted: list[str] = []
        for u in self._upstreams:
            accepted.append(f"/{u.provider}/")
            accepted.extend(u.adapter.path_prefixes)
        return tuple(accepted)

    def resolve(self, path: str) -> Resolution | None:
        # Style 1: explicit provider URL prefix.
        for upstream in self._upstreams:
            tag = f"/{upstream.provider}/"
            if path.startswith(tag):
                rewritten = "/" + path[len(tag) :]
                return Resolution(upstream=upstream, rewritten_path=rewritten)
            if path == f"/{upstream.provider}":
                return Resolution(upstream=upstream, rewritten_path="/")

        # Style 2: provider path-prefix.
        for upstream in self._upstreams:
            for prefix in upstream.adapter.path_prefixes:
                if path.startswith(prefix):
                    return Resolution(upstream=upstream, rewritten_path=path)
        return None

    @classmethod
    def from_config(cls, config: ProxyConfig) -> Router:
        return cls(
            [
                Upstream(
                    provider=openai_adapter.name,
                    base_url=config.openai_upstream,
                    adapter=openai_adapter,
                ),
                Upstream(
                    provider=anthropic_adapter.name,
                    base_url=config.anthropic_upstream,
                    adapter=anthropic_adapter,
                ),
                Upstream(
                    provider=gemini_adapter.name,
                    base_url=config.gemini_upstream,
                    adapter=gemini_adapter,
                ),
            ]
        )
