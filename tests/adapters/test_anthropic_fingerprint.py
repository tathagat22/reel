"""Anthropic adapter fingerprint stability — including Claude Code drift.

Claude Code (the CLI binary) injects non-deterministic content into the system
prompt and user messages on every invocation:

* a per-session ``cch=<hex>`` cache-marker token in the billing header
* the available-skills list, which is both reordered AND partially truncated
  (some entries listed as ``- name: <description>`` and some as bare
  ``- name``) between invocations

Without normalization those bytes flow into the fingerprint and replay never
hits, even for identical user-facing prompts. These tests pin the
normalization behavior.
"""

from __future__ import annotations

import json
from typing import Any

from reel.adapters.anthropic import fingerprint

MESSAGES_ENDPOINT = "/v1/messages"


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode()


def _cc_body(*, cch: str, skills: list[str], user_text: str = "hi") -> dict[str, Any]:
    """A minimal Anthropic request body that mimics Claude Code's structure."""
    skills_block = (
        "<system-reminder>\nThe following skills are available for use with the Skill tool:\n\n"
    )
    skills_block += "\n".join(skills) + "\n</system-reminder>"
    return {
        "model": "claude-haiku-4-5",
        "system": [
            {
                "type": "text",
                "text": f"x-anthropic-billing-header: cc_version=2.1.0; cc_entrypoint=sdk-cli; cch={cch};",
            },
            {"type": "text", "text": "You are a Claude agent."},
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": skills_block},
                    {"type": "text", "text": user_text},
                ],
            }
        ],
        "stream": True,
    }


def test_basic_anthropic_fingerprint_returns_prefixed_sha256() -> None:
    h = fingerprint(
        _body({"model": "claude-haiku-4-5", "messages": []}),
        endpoint=MESSAGES_ENDPOINT,
    )
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_metadata_is_ignored() -> None:
    a = _body({"model": "claude-haiku-4-5", "messages": [], "metadata": {"user_id": "alice"}})
    b = _body({"model": "claude-haiku-4-5", "messages": [], "metadata": {"user_id": "bob"}})
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) == fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_stream_field_is_ignored() -> None:
    a = _body({"model": "claude-haiku-4-5", "messages": [], "stream": True})
    b = _body({"model": "claude-haiku-4-5", "messages": [], "stream": False})
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) == fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_non_claude_code_traffic_is_unaffected_by_normalization() -> None:
    """Same byte sequence in, same fingerprint out — the normalization is a no-op
    for traffic that doesn't carry Claude Code's signature."""
    body = _body(
        {
            "model": "claude-haiku-4-5",
            "messages": [{"role": "user", "content": "Sort these: c, a, b"}],
        }
    )
    assert fingerprint(body, endpoint=MESSAGES_ENDPOINT) == fingerprint(
        body, endpoint=MESSAGES_ENDPOINT
    )


def test_non_cc_text_with_dash_bullets_is_not_reordered() -> None:
    """A non-Claude-Code request whose user prompt happens to contain ``- foo``
    bullet lines must not have those lines reordered — the normalization should
    only fire when the billing-header signature is present."""
    a = _body(
        {
            "model": "claude-haiku-4-5",
            "messages": [
                {"role": "user", "content": "- charlie: third\n- alpha: first\n- bravo: second"}
            ],
        }
    )
    b = _body(
        {
            "model": "claude-haiku-4-5",
            "messages": [
                {"role": "user", "content": "- alpha: first\n- bravo: second\n- charlie: third"}
            ],
        }
    )
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) != fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_cch_cache_marker_is_normalized_for_claude_code() -> None:
    a = _body(_cc_body(cch="078a5", skills=["- foo", "- bar"]))
    b = _body(_cc_body(cch="a5f94", skills=["- foo", "- bar"]))
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) == fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_skills_list_order_is_normalized_for_claude_code() -> None:
    a = _body(
        _cc_body(
            cch="abc",
            skills=[
                "- skill-a: alpha description",
                "- skill-b: bravo description",
                "- skill-c: charlie description",
            ],
        )
    )
    b = _body(
        _cc_body(
            cch="abc",
            skills=[
                "- skill-c: charlie description",
                "- skill-a: alpha description",
                "- skill-b: bravo description",
            ],
        )
    )
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) == fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_skills_list_truncation_is_normalized_for_claude_code() -> None:
    """Claude Code sometimes lists ``- name: full description`` and sometimes
    just ``- name`` for the same skill. Both forms must fingerprint identically."""
    a = _body(
        _cc_body(
            cch="abc",
            skills=[
                "- figma:figma-generate-library: Build or update a design system in Figma.",
                "- figma:figma-implement-design",
            ],
        )
    )
    b = _body(
        _cc_body(
            cch="abc",
            skills=[
                "- figma:figma-generate-library",
                "- figma:figma-implement-design: Translates Figma designs into code.",
            ],
        )
    )
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) == fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_different_user_prompts_still_fingerprint_differently_under_cc() -> None:
    """Sanity check: normalization must NOT collapse meaningfully different
    requests. Different user prompts → different fingerprints."""
    a = _body(_cc_body(cch="abc", skills=["- s1"], user_text="explain TCP"))
    b = _body(_cc_body(cch="abc", skills=["- s1"], user_text="explain UDP"))
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) != fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_different_skill_sets_still_fingerprint_differently_under_cc() -> None:
    """Adding a new skill (not just reordering) changes the prompt and must
    produce a different fingerprint."""
    a = _body(_cc_body(cch="abc", skills=["- s1", "- s2"]))
    b = _body(_cc_body(cch="abc", skills=["- s1", "- s2", "- s3"]))
    assert fingerprint(a, endpoint=MESSAGES_ENDPOINT) != fingerprint(b, endpoint=MESSAGES_ENDPOINT)


def test_tools_array_is_dropped_for_claude_code() -> None:
    """Claude Code lazy-loads MCP tools — the tools array shape varies between
    invocations. We strip it from CC fingerprints so the same user prompt
    matches across runs even when different MCP servers happen to be loaded."""
    base = _cc_body(cch="abc", skills=["- s1"], user_text="hi")
    a = dict(base)
    a["tools"] = [{"name": "Read", "description": "read", "input_schema": {}}]
    b = dict(base)
    b["tools"] = [
        {"name": "Read", "description": "read", "input_schema": {}},
        {"name": "mcp__gmail__send", "description": "send mail", "input_schema": {}},
    ]
    assert fingerprint(_body(a), endpoint=MESSAGES_ENDPOINT) == fingerprint(
        _body(b), endpoint=MESSAGES_ENDPOINT
    )


def test_tools_array_is_preserved_for_non_claude_code() -> None:
    """Third-party Anthropic SDK apps register their own tool sets — those
    affect what the model can do and must remain part of the fingerprint."""
    base: dict[str, Any] = {
        "model": "claude-haiku-4-5",
        "messages": [{"role": "user", "content": "hi"}],
    }
    a = dict(base)
    a["tools"] = [{"name": "Read", "description": "read", "input_schema": {}}]
    b = dict(base)
    b["tools"] = [{"name": "Write", "description": "write", "input_schema": {}}]
    assert fingerprint(_body(a), endpoint=MESSAGES_ENDPOINT) != fingerprint(
        _body(b), endpoint=MESSAGES_ENDPOINT
    )
