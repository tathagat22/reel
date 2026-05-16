"""Sprint 3.6 — secret pattern coverage.

Test fixtures embed obvious ``FAKE_FIXTURE`` markers and stay just below the
exact lengths used by GitHub's secret scanner so legitimate test data isn't
flagged as a public leak. Our regexes use ``{20,}`` / ``{30,}`` lower bounds
on purpose — they still match these fixtures.
"""

from __future__ import annotations

import pytest

from reel.redact.secrets import contains_secret, redact_secrets

# Below: every fixture has "FAKE" baked in so it can't be mistaken for a real
# key by either a reader or an automated scanner.
_FAKE_OPENAI = "sk-FAKE_FIXTURE_TEST_ONLY_NOT_REAL"
_FAKE_OPENAI_PROJECT = "sk-proj-FAKE_FIXTURE_TEST_ONLY_NOT_REAL"
_FAKE_ANTHROPIC = "sk-ant-api03-FAKE_FIXTURE_TEST_ONLY_NOT_REAL"
# GitHub's Google detector looks for `AIza[A-Za-z0-9_-]{35}` (exact). Our regex
# uses {30,}. Keeping the suffix at 30 chars matches us but not GitHub.
_FAKE_GOOGLE = "AIzaFAKEFIXTUREONLYNOTREALFORTESTS"  # AIza + 30 alphanumerics
# GitHub PATs are alphanumeric only after the prefix (no underscores).
_FAKE_GITHUB_CLASSIC = "ghp_FAKEFIXTURETESTONLYNOTREALAA12"
_FAKE_GITHUB_SERVER = "ghs_FAKEFIXTURETESTONLYNOTREALAA12"


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        (_FAKE_OPENAI, "openai-key"),
        (_FAKE_OPENAI_PROJECT, "openai-project-key"),
        (_FAKE_ANTHROPIC, "anthropic-key"),
        (_FAKE_GOOGLE, "google-api-key"),
        (_FAKE_GITHUB_CLASSIC, "github-pat"),
        (_FAKE_GITHUB_SERVER, "github-pat"),
        ("AKIAIOSFODNN7EXAMPLE", "aws-access-key"),  # AWS canonical example
        ("xoxb-1234567890-abc-def-ghi", "slack-token"),
    ],
)
def test_known_key_shapes_redacted(raw: str, label: str) -> None:
    assert contains_secret(raw)
    out = redact_secrets(raw)
    assert raw not in out
    assert label in out


def test_bearer_token_redacted() -> None:
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.FAKE_TEST_FIXTURE.sig"
    out = redact_secrets(raw)
    assert "FAKE_TEST_FIXTURE" not in out
    assert "Bearer [redacted]" in out


def test_safe_text_passes_through() -> None:
    out = redact_secrets("this is a normal sentence with no secrets")
    assert out == "this is a normal sentence with no secrets"


def test_bearer_followed_by_short_english_word_is_not_redacted() -> None:
    """The Bearer pattern must not eat ordinary English prose like ``Bearer
    tokens``, ``Bearer is a header``, etc. Real bearer tokens are always
    longer than 20 chars; the regex requires that floor so summaries and
    documentation that mention bearer-token concepts pass through untouched."""
    cases = [
        "the Bearer tokens are scrubbed at capture time",
        "headers like Bearer are stripped",
        "Bearer is one HTTP auth scheme",
        "Bearer abc",  # 3-char token — too short to be a real one
    ]
    for raw in cases:
        out = redact_secrets(raw)
        assert out == raw, f"unexpected redaction: {raw!r} -> {out!r}"
        assert not contains_secret(raw), f"unexpected secret detected in {raw!r}"


def test_long_bearer_token_still_redacted() -> None:
    """Sanity check the floor — anything 20+ chars after ``Bearer `` is still
    treated as a token, so we don't regress on the real-secret case."""
    raw = "Authorization: Bearer FAKEFIXTURETOKENWITHTWENTYPLUSCHARS"
    out = redact_secrets(raw)
    assert "FAKEFIXTURETOKENWITHTWENTYPLUSCHARS" not in out
    assert "Bearer [redacted]" in out


def test_multiple_secrets_in_one_string() -> None:
    raw = f"{_FAKE_OPENAI} and {_FAKE_GITHUB_CLASSIC}"
    out = redact_secrets(raw)
    assert _FAKE_OPENAI not in out
    assert _FAKE_GITHUB_CLASSIC not in out
    assert "[redacted:openai-key]" in out
    assert "[redacted:github-pat]" in out
