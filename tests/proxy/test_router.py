"""Sprint 3.2 — multi-provider routing tests."""

from __future__ import annotations

from reel.adapters.anthropic import adapter as anthropic_adapter
from reel.adapters.openai import OPENAI_PATH_PREFIXES
from reel.adapters.openai import adapter as openai_adapter
from reel.proxy.config import ProxyConfig
from reel.proxy.router import Router, Upstream


def test_from_config_includes_all_known_providers() -> None:
    router = Router.from_config(ProxyConfig())
    providers = {u.provider for u in router.upstreams}
    assert providers == {"openai", "anthropic", "gemini"}


def test_path_prefix_routes_openai_chat() -> None:
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/v1/chat/completions")
    assert res is not None
    assert res.upstream.provider == "openai"
    assert res.rewritten_path == "/v1/chat/completions"


def test_path_prefix_routes_anthropic_messages() -> None:
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/v1/messages")
    assert res is not None
    assert res.upstream.provider == "anthropic"
    assert res.rewritten_path == "/v1/messages"


def test_unknown_path_returns_none() -> None:
    router = Router.from_config(ProxyConfig())
    assert router.resolve("/random/path") is None
    assert router.resolve("/admin/secret") is None


def test_explicit_provider_prefix_routes_anthropic() -> None:
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/anthropic/v1/messages")
    assert res is not None
    assert res.upstream.provider == "anthropic"
    # Provider prefix stripped before forwarding upstream.
    assert res.rewritten_path == "/v1/messages"


def test_explicit_provider_prefix_routes_openai() -> None:
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/openai/v1/chat/completions")
    assert res is not None
    assert res.upstream.provider == "openai"
    assert res.rewritten_path == "/v1/chat/completions"


def test_explicit_prefix_disambiguates_shared_path() -> None:
    """`/v1/models` is in OpenAI's list; explicit `/anthropic/v1/models` wins for Anthropic."""
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/anthropic/v1/models")
    assert res is not None
    assert res.upstream.provider == "anthropic"
    assert res.rewritten_path == "/v1/models"


def test_bare_provider_path_routes_with_root_rewrite() -> None:
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/anthropic")
    assert res is not None
    assert res.upstream.provider == "anthropic"
    assert res.rewritten_path == "/"


def test_resolve_accepts_bare_chat_path_without_v1_prefix() -> None:
    """Some users set OPENAI_BASE_URL=http://localhost:7878 (without /v1)."""
    router = Router.from_config(ProxyConfig())
    res = router.resolve("/chat/completions")
    assert res is not None
    assert res.upstream.provider == "openai"


def test_custom_upstreams() -> None:
    custom = [
        Upstream(provider="openai", base_url="https://example.com", adapter=openai_adapter),
    ]
    router = Router(custom)
    assert router.resolve("/v1/chat/completions") is not None
    assert router.resolve("/v1/messages") is None  # Anthropic not registered.


def test_allowed_prefixes_diagnostic_lists_everything() -> None:
    router = Router.from_config(ProxyConfig())
    prefixes = router.allowed_prefixes
    # Provider tags appear.
    assert "/openai/" in prefixes
    assert "/anthropic/" in prefixes
    # Provider path prefixes appear too.
    assert all(p in prefixes for p in OPENAI_PATH_PREFIXES)
    assert all(p in prefixes for p in anthropic_adapter.path_prefixes)
