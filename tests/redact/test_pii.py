"""Sprint 3.7 — PII pattern coverage."""

from __future__ import annotations

import pytest

from reel.redact.pii import contains_pii, redact_pii


@pytest.mark.parametrize(
    "raw",
    [
        "alice@example.com",
        "alice.bob+test@sub.example.co.uk",
        "USER+TAG@example.io",
    ],
)
def test_emails_redacted(raw: str) -> None:
    out = redact_pii(raw)
    assert raw not in out
    assert "[redacted:email]" in out


@pytest.mark.parametrize(
    "raw",
    [
        "+1 555-555-5555",
        "(555) 555-5555",
        "555.555.5555",
        "5555555555",
        "+15555555555",
    ],
)
def test_phones_redacted(raw: str) -> None:
    assert contains_pii(raw)
    out = redact_pii(raw)
    assert raw not in out
    assert "[redacted:phone]" in out


def test_safe_text_passes_through() -> None:
    out = redact_pii("the alice in wonderland book is fine")
    assert "[redacted" not in out
