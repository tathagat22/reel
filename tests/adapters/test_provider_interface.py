"""Sprint 3.1 — ProviderAdapter interface + OpenAIAdapter."""

from __future__ import annotations

import json

from reel.adapters.base import ProviderAdapter
from reel.adapters.openai import (
    OPENAI_PATH_PREFIXES,
    OpenAIAdapter,
    adapter,
    fingerprint,
)


def test_openai_adapter_is_provider_adapter() -> None:
    a = OpenAIAdapter()
    assert isinstance(a, ProviderAdapter)


def test_openai_adapter_name() -> None:
    assert OpenAIAdapter().name == "openai"


def test_openai_adapter_path_prefixes() -> None:
    a = OpenAIAdapter()
    prefixes = a.path_prefixes
    assert prefixes == OPENAI_PATH_PREFIXES
    # Core OpenAI endpoints are routable.
    assert any(p.startswith("/v1/chat") for p in prefixes)
    assert any(p.startswith("/v1/embeddings") for p in prefixes)
    # Without-/v1 variants are also present (SDK-managed base URL).
    assert "/chat/" in prefixes


def test_openai_adapter_fingerprint_matches_free_function() -> None:
    body = json.dumps({"model": "gpt-5", "messages": []}).encode()
    a = OpenAIAdapter()
    assert a.fingerprint(body, endpoint="/v1/chat/completions") == fingerprint(
        body, endpoint="/v1/chat/completions"
    )


def test_module_level_singleton() -> None:
    """`adapter` is exported as a ready-to-use singleton."""
    assert isinstance(adapter, ProviderAdapter)
    assert adapter.name == "openai"


def test_provider_adapter_cannot_be_instantiated_directly() -> None:
    import pytest

    with pytest.raises(TypeError):
        ProviderAdapter()  # type: ignore[abstract]
