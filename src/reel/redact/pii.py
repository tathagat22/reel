"""PII pattern detection and scrubbing.

Detects:

* **Email addresses** — RFC-ish, matches the vast majority of real addresses.
* **US-style phone numbers** — ``+1 555-555-5555``, ``(555) 555-5555``,
  ``5555555555``, etc.

International phone formats and other PII (SSN, credit card, addresses) are
not covered in this default set — extend ``PII_PATTERNS`` as your threat
model requires.
"""

from __future__ import annotations

import re

PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[redacted:email]",
    ),
    (
        re.compile(
            r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        ),
        "[redacted:phone]",
    ),
]


def redact_pii(text: str) -> str:
    out = text
    for pattern, replacement in PII_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def contains_pii(text: str) -> bool:
    return any(p.search(text) for p, _ in PII_PATTERNS)
