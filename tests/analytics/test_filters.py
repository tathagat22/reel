"""Sprint 5.1 — filter primitives."""

from __future__ import annotations

import re

from reel.analytics.filters import FilterSpec, apply
from reel.cassette.schema import (
    CassetteEntry,
    CassetteRequest,
    CassetteResponse,
    StreamChunk,
)
from reel.cassette.writer import generate_id, now_iso


def _entry(
    *,
    provider: str = "openai",
    path: str = "/v1/chat/completions",
    model: str | None = "gpt-5",
    status: int = 200,
    request_body: dict[str, object] | None = None,
    response_body: dict[str, object] | None = None,
    stream_chunks: list[StreamChunk] | None = None,
) -> CassetteEntry:
    body: dict[str, object] = request_body or {"messages": []}
    if model is not None:
        body = {"model": model, **body}
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(method="POST", path=path, fingerprint="sha256:x", body=body),
        response=CassetteResponse(
            status=status,
            headers={},
            body=response_body if stream_chunks is None else None,
            stream_chunks=stream_chunks,
        ),
    )


def test_no_filter_yields_everything() -> None:
    entries = [_entry(), _entry(provider="anthropic"), _entry(provider="gemini")]
    assert list(apply(FilterSpec(), entries)) == entries


def test_provider_filter() -> None:
    entries = [_entry(provider="openai"), _entry(provider="anthropic")]
    out = list(apply(FilterSpec(provider="anthropic"), entries))
    assert len(out) == 1
    assert out[0].provider == "anthropic"


def test_model_substring_match_is_case_insensitive() -> None:
    entries = [_entry(model="gpt-5-turbo"), _entry(model="claude-opus-4-7")]
    assert len(list(apply(FilterSpec(model="GPT"), entries))) == 1
    assert len(list(apply(FilterSpec(model="opus"), entries))) == 1


def test_status_class_filter() -> None:
    entries = [_entry(status=200), _entry(status=429), _entry(status=503)]
    assert len(list(apply(FilterSpec(status="2xx"), entries))) == 1
    assert len(list(apply(FilterSpec(status="4xx"), entries))) == 1
    assert len(list(apply(FilterSpec(status="5xx"), entries))) == 1


def test_status_exact_filter() -> None:
    entries = [_entry(status=429), _entry(status=200)]
    out = list(apply(FilterSpec(status="429"), entries))
    assert len(out) == 1
    assert out[0].response.status == 429


def test_has_tool_call_request_side() -> None:
    with_tools = _entry(request_body={"tools": [{"type": "function"}]})
    without = _entry()
    out = list(apply(FilterSpec(has_tool_call=True), [with_tools, without]))
    assert out == [with_tools]


def test_has_tool_call_response_side() -> None:
    with_tool_calls = _entry(
        response_body={"choices": [{"message": {"content": None, "tool_calls": [{"id": "c"}]}}]}
    )
    without = _entry(response_body={"choices": [{"message": {"content": "hi"}}]})
    out = list(apply(FilterSpec(has_tool_call=True), [with_tool_calls, without]))
    assert out == [with_tool_calls]


def test_has_tool_call_stream_side() -> None:
    chunks = [StreamChunk(data={"delta": {"tool_calls": [{"id": "c"}]}}, t_offset_ms=0)]
    streaming = _entry(stream_chunks=chunks)
    out = list(apply(FilterSpec(has_tool_call=True), [streaming, _entry()]))
    assert out == [streaming]


def test_has_tool_call_negated() -> None:
    plain = _entry()
    out = list(apply(FilterSpec(has_tool_call=False), [plain]))
    assert out == [plain]


def test_regex_filter_searches_serialized_entry() -> None:
    entries = [
        _entry(response_body={"id": "needle-here"}),
        _entry(response_body={"id": "haystack"}),
    ]
    out = list(apply(FilterSpec(regex=re.compile("needle")), entries))
    assert len(out) == 1


def test_limit_is_streaming_head_cut() -> None:
    entries = [_entry() for _ in range(10)]
    out = list(apply(FilterSpec(limit=3), entries))
    assert len(out) == 3


def test_filters_compose_with_and_semantics() -> None:
    entries = [
        _entry(provider="openai", status=200),
        _entry(provider="anthropic", status=429),
        _entry(provider="openai", status=429),
    ]
    out = list(apply(FilterSpec(provider="openai", status="4xx"), entries))
    assert len(out) == 1
    assert out[0].provider == "openai"
    assert out[0].response.status == 429
