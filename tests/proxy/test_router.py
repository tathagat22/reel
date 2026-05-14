"""Sprint 1.2 — router resolution."""

from __future__ import annotations

from reel.proxy.config import ProxyConfig
from reel.proxy.router import OPENAI_ALLOWED_PREFIXES, Router, Upstream


def test_from_config_uses_configured_openai_upstream() -> None:
    cfg = ProxyConfig(openai_upstream="https://api.openai.com")
    router = Router.from_config(cfg)

    assert router.upstream == Upstream(provider="openai", base_url="https://api.openai.com")
    assert router.allowed_prefixes == OPENAI_ALLOWED_PREFIXES


def test_resolve_returns_upstream_for_v1_paths() -> None:
    router = Router.from_config(ProxyConfig())

    upstream = router.resolve("/v1/chat/completions")
    assert upstream is not None
    assert upstream.provider == "openai"


def test_resolve_returns_none_for_unknown_paths() -> None:
    router = Router.from_config(ProxyConfig())

    assert router.resolve("/random/path") is None
    assert router.resolve("/admin/secret") is None


def test_resolve_accepts_bare_chat_path_without_v1_prefix() -> None:
    """Some users set OPENAI_BASE_URL=http://localhost:7878 (without /v1)."""
    router = Router.from_config(ProxyConfig())
    assert router.resolve("/chat/completions") is not None


def test_custom_allowed_prefixes() -> None:
    router = Router(
        upstream=Upstream(provider="custom", base_url="https://example.com"),
        allowed_prefixes=("/api/",),
    )
    assert router.resolve("/api/foo") is not None
    assert router.resolve("/v1/chat/completions") is None
