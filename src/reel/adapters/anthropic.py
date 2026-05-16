"""Anthropic provider adapter.

Anthropic's HTTP API lives under ``/v1/messages*``. ``/v1/models`` exists too
but conflicts with OpenAI's ``/v1/models`` — explicit ``/anthropic/`` URL
prefix routing (Sprint 3.2 router) is the way to disambiguate that case.

Ignored fingerprint keys are minimal — only the wire-protocol fields that
don't change generated content:

* ``stream`` — delivery transport
* ``metadata`` — logging only

The fingerprint pass also normalizes a small set of Claude-Code-specific
volatile content (cache-version markers and a non-deterministic skills
list embedded in the system prompt) so that two byte-different invocations
of the same Claude Code session prompt hash identically. The normalization
only fires when Claude Code's signature is detected; non-CC Anthropic traffic
is untouched.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from reel.adapters._fingerprint import compute_fingerprint
from reel.adapters.base import ProviderAdapter

FINGERPRINT_IGNORE: frozenset[str] = frozenset(
    {
        "stream",
        "metadata",
    }
)

# Path prefixes for Anthropic. ``/v1/models`` is intentionally omitted to
# avoid colliding with OpenAI; users hitting Anthropic's models endpoint
# should use the explicit ``/anthropic/v1/models`` URL prefix.
ANTHROPIC_PATH_PREFIXES: tuple[str, ...] = (
    "/v1/messages",
    "/v1/complete",
)


_CC_BILLING_MARKER = "x-anthropic-billing-header"
_CC_ENTRYPOINT_MARKER = "cc_entrypoint="
_CCH_PATTERN = re.compile(r"cch=[a-f0-9]+;?")
_SKILLS_HEADER = "The following skills are available for use with the Skill tool:"
# Strip everything from the first ": " onwards (description). Skill names like
# "figma:figma-code-connect" contain bare colons (no space), so this preserves them.
_SKILL_DESCRIPTION_PATTERN = re.compile(r":\s.*$")


def _has_claude_code_signature(body: dict[str, Any]) -> bool:
    """Detect Claude Code by its signature billing header in the system prompt."""
    sys_blocks = body.get("system")
    if not isinstance(sys_blocks, list):
        return False
    for blk in cast(list[Any], sys_blocks):
        if not isinstance(blk, dict):
            continue
        text = cast(dict[str, Any], blk).get("text")
        if isinstance(text, str) and _CC_BILLING_MARKER in text and _CC_ENTRYPOINT_MARKER in text:
            return True
    return False


def _normalize_skills_list(text: str) -> str:
    """Sort and de-duplicate the skill bullet list inside a system-reminder block.

    Claude Code lists available skills inline as ``- skill-name: description``
    lines, but the ordering varies between invocations and some entries are
    truncated (just ``- skill-name`` with no description) when the skill has
    already been loaded earlier in the session. We collapse each line to
    ``- skill-name`` and sort, so the same set of skills always serializes
    the same way.
    """
    if _SKILLS_HEADER not in text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    block: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith("- "):
            in_block = True
            block.append(_SKILL_DESCRIPTION_PATTERN.sub("", line.rstrip()))
        else:
            if in_block:
                out.extend(sorted(set(block)))
                block = []
                in_block = False
            out.append(line)
    if block:
        out.extend(sorted(set(block)))
    return "\n".join(out)


def _normalize_claude_code_volatile(body: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied body with Claude Code's volatile content rewritten.

    Two known sources of drift:
    1. ``cch=<hex>`` cache marker inside the billing-header system block.
    2. Skill list ordering and truncation inside user-message text blocks.
    """
    normalized: dict[str, Any] = json.loads(json.dumps(body))

    sys_blocks = normalized.get("system")
    if isinstance(sys_blocks, list):
        for blk in cast(list[Any], sys_blocks):
            if isinstance(blk, dict):
                text = cast(dict[str, Any], blk).get("text")
                if isinstance(text, str) and _CC_BILLING_MARKER in text:
                    cast(dict[str, Any], blk)["text"] = _CCH_PATTERN.sub("cch=", text)

    messages = normalized.get("messages")
    if isinstance(messages, list):
        for msg in cast(list[Any], messages):
            if not isinstance(msg, dict):
                continue
            content = cast(dict[str, Any], msg).get("content")
            if not isinstance(content, list):
                continue
            for blk in cast(list[Any], content):
                if isinstance(blk, dict):
                    text = cast(dict[str, Any], blk).get("text")
                    if isinstance(text, str):
                        cast(dict[str, Any], blk)["text"] = _normalize_skills_list(text)

    return normalized


def _maybe_normalize_for_fingerprint(body: bytes) -> bytes:
    """If the body looks like Claude Code traffic, return a normalized form.

    Falls back to the original bytes on parse error or when no Claude Code
    signature is present — so non-CC Anthropic requests are unaffected.
    """
    if not body:
        return body
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(parsed, dict):
        return body
    parsed_dict = cast(dict[str, Any], parsed)
    if not _has_claude_code_signature(parsed_dict):
        return body
    normalized = _normalize_claude_code_volatile(parsed_dict)
    return json.dumps(normalized, separators=(",", ":"), ensure_ascii=False).encode()


def fingerprint(body: bytes, *, endpoint: str = "") -> str:
    return compute_fingerprint(
        _maybe_normalize_for_fingerprint(body),
        endpoint=endpoint,
        ignore_keys=FINGERPRINT_IGNORE,
    )


class AnthropicAdapter(ProviderAdapter):
    """Anthropic provider implementation of :class:`ProviderAdapter`."""

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def path_prefixes(self) -> tuple[str, ...]:
        return ANTHROPIC_PATH_PREFIXES

    def fingerprint(self, body: bytes, *, endpoint: str) -> str:
        return fingerprint(body, endpoint=endpoint)

    @property
    def fingerprint_ignore(self) -> frozenset[str]:
        return FINGERPRINT_IGNORE


adapter: ProviderAdapter = AnthropicAdapter()
