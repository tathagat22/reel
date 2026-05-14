"""Sprint 3.6 — secret pattern coverage."""

from __future__ import annotations

import pytest

from reel.redact.secrets import contains_secret, redact_secrets


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("sk-AAAAAAAAAAAAAAAAAAAAAA", "openai-key"),
        ("sk-proj-AAAAAAAAAAAAAAAAAAAAAA", "openai-project-key"),
        ("sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "anthropic-key"),
        ("AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "google-api-key"),
        ("ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "github-pat"),
        ("ghs_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "github-pat"),
        ("AKIAIOSFODNN7EXAMPLE", "aws-access-key"),
        ("xoxb-1234567890-abc-def-ghi", "slack-token"),
    ],
)
def test_known_key_shapes_redacted(raw: str, label: str) -> None:
    assert contains_secret(raw)
    out = redact_secrets(raw)
    assert raw not in out
    assert label in out


def test_bearer_token_redacted() -> None:
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    out = redact_secrets(raw)
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "Bearer [redacted]" in out


def test_safe_text_passes_through() -> None:
    out = redact_secrets("this is a normal sentence with no secrets")
    assert out == "this is a normal sentence with no secrets"


def test_multiple_secrets_in_one_string() -> None:
    raw = "sk-AAAAAAAAAAAAAAAAAAAA and ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    out = redact_secrets(raw)
    assert "sk-AAAAAAAAAAAAAAAAAAAA" not in out
    assert "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in out
    assert "[redacted:openai-key]" in out
    assert "[redacted:github-pat]" in out
