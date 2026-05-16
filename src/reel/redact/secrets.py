"""Secret pattern detection and scrubbing.

Conservative regex set covering common API key and bearer-token formats.
Patterns are deliberately greedy on the "looks like a token" side and narrow
on the "matches a key prefix" side, so we avoid scrubbing arbitrary text
that happens to contain hex.

If a pattern misses a real secret, the cassette will still ship that secret —
detection must be *conservative-but-comprehensive*. PRs welcome to extend the
set with proof of a missed match.
"""

from __future__ import annotations

import re

# Each tuple is (compiled-regex, replacement-label).
#
# Order matters — more-specific patterns must come before more-general ones.
# `sk-ant-api...` and `sk-proj-...` are matched first so the catch-all `sk-...`
# OpenAI rule doesn't swallow them.
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Anthropic — more specific prefix than the OpenAI sk- rule below.
    (re.compile(r"sk-ant-api\d+-[A-Za-z0-9_\-]+"), "[redacted:anthropic-key]"),
    # OpenAI project-scoped keys (more specific than the catch-all).
    (re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"), "[redacted:openai-project-key]"),
    # OpenAI standard keys — catch-all, must run last among sk- patterns.
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "[redacted:openai-key]"),
    # Google / Gemini API keys.
    (re.compile(r"AIza[A-Za-z0-9_\-]{30,}"), "[redacted:google-api-key]"),
    # GitHub PATs.
    (re.compile(r"gh[ps]_[A-Za-z0-9]{30,}"), "[redacted:github-pat]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{50,}"), "[redacted:github-pat-fine]"),
    # AWS access keys.
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[redacted:aws-access-key]"),
    # Slack tokens.
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]+"), "[redacted:slack-token]"),
    # Generic Bearer header — case-insensitive prefix, captures everything after.
    # The 20-char minimum on the token body avoids catching English prose like
    # "Bearer tokens" or "Bearer is a method" when the response body explains
    # what a Bearer token is. Real-world bearer tokens (JWTs, OAuth access
    # tokens) are virtually always longer than 20 chars.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=:+/]{20,}"), "Bearer [redacted]"),
]


def redact_secrets(text: str) -> str:
    """Replace every detected secret pattern with a redaction label."""
    out = text
    for pattern, replacement in SECRET_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def contains_secret(text: str) -> bool:
    """Fast check — does this text contain anything that *looks* like a secret?"""
    return any(p.search(text) for p, _ in SECRET_PATTERNS)
