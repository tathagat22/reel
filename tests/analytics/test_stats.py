"""Sprint 5.5 — aggregate statistics over a cassette."""

from __future__ import annotations

from reel.analytics.stats import StatsSummary, TTFTDistribution, aggregate
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
    status: int = 200,
    response_body: dict[str, object] | None = None,
    stream_chunks: list[StreamChunk] | None = None,
) -> CassetteEntry:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(
            method="POST", path="/v1/chat/completions", fingerprint="sha256:x", body={}
        ),
        response=CassetteResponse(
            status=status,
            headers={},
            body=response_body if stream_chunks is None else None,
            stream_chunks=stream_chunks,
        ),
    )


# ─── Empty / safe defaults ─────────────────────────────────────────────


def test_aggregate_over_zero_entries_is_safe() -> None:
    summary = aggregate([])
    assert isinstance(summary, StatsSummary)
    assert summary.total == 0
    assert summary.by_provider == {}
    assert summary.by_status_class == {}
    # No division-by-zero.
    assert summary.error_rate == 0.0
    assert summary.input_tokens == 0
    assert summary.output_tokens == 0
    assert summary.total_tokens == 0
    assert summary.ttft == TTFTDistribution(count=0)


def test_dataclasses_are_frozen() -> None:
    summary = aggregate([])
    try:
        summary.total = 99  # type: ignore[misc]
    except Exception as exc:  # FrozenInstanceError
        assert "frozen" in str(exc).lower() or "FrozenInstanceError" in type(exc).__name__
    else:
        raise AssertionError("StatsSummary should be frozen")


# ─── Error rate ────────────────────────────────────────────────────────


def test_error_rate_mixed_status_codes() -> None:
    entries = [
        _entry(status=200),
        _entry(status=200),
        _entry(status=200),
        _entry(status=429),  # 4xx
    ]
    summary = aggregate(entries)
    assert summary.total == 4
    assert summary.by_status_class == {"2xx": 3, "4xx": 1}
    assert summary.error_rate == 0.25


def test_error_rate_counts_5xx_and_3xx_as_errors() -> None:
    entries = [
        _entry(status=200),
        _entry(status=302),  # 3xx, non-2xx → error
        _entry(status=500),
    ]
    summary = aggregate(entries)
    assert summary.error_rate == 2 / 3
    assert summary.by_status_class == {"2xx": 1, "3xx": 1, "5xx": 1}


def test_error_rate_all_errors() -> None:
    entries = [_entry(status=500), _entry(status=503)]
    summary = aggregate(entries)
    assert summary.error_rate == 1.0


# ─── Provider counts ───────────────────────────────────────────────────


def test_per_provider_counts_multi_provider() -> None:
    entries = [
        _entry(provider="openai"),
        _entry(provider="openai"),
        _entry(provider="anthropic"),
        _entry(provider="gemini"),
        _entry(provider="gemini"),
        _entry(provider="gemini"),
    ]
    summary = aggregate(entries)
    assert summary.by_provider == {"openai": 2, "anthropic": 1, "gemini": 3}
    assert summary.total == 6


# ─── Token extraction ──────────────────────────────────────────────────


def test_tokens_openai_shape() -> None:
    entry = _entry(
        response_body={"usage": {"prompt_tokens": 100, "completion_tokens": 25}},
    )
    summary = aggregate([entry])
    assert summary.input_tokens == 100
    assert summary.output_tokens == 25
    assert summary.total_tokens == 125


def test_tokens_anthropic_shape() -> None:
    entry = _entry(
        provider="anthropic",
        response_body={"usage": {"input_tokens": 50, "output_tokens": 80}},
    )
    summary = aggregate([entry])
    assert summary.input_tokens == 50
    assert summary.output_tokens == 80


def test_tokens_gemini_shape() -> None:
    entry = _entry(
        provider="gemini",
        response_body={
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 22,
            }
        },
    )
    summary = aggregate([entry])
    assert summary.input_tokens == 11
    assert summary.output_tokens == 22


def test_tokens_missing_usage_contributes_zero() -> None:
    entry = _entry(response_body={"id": "no-usage-here"})
    summary = aggregate([entry])
    assert summary.input_tokens == 0
    assert summary.output_tokens == 0


def test_tokens_summed_across_providers() -> None:
    entries = [
        _entry(response_body={"usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
        _entry(
            provider="anthropic",
            response_body={"usage": {"input_tokens": 7, "output_tokens": 3}},
        ),
        _entry(
            provider="gemini",
            response_body={"usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1}},
        ),
    ]
    summary = aggregate(entries)
    assert summary.input_tokens == 19
    assert summary.output_tokens == 9
    assert summary.total_tokens == 28


def test_tokens_extracted_from_last_stream_chunk() -> None:
    chunks = [
        StreamChunk(data={"delta": "Hello"}, t_offset_ms=100),
        StreamChunk(
            data={"usage": {"prompt_tokens": 42, "completion_tokens": 8}},
            t_offset_ms=300,
        ),
    ]
    summary = aggregate([_entry(stream_chunks=chunks)])
    assert summary.input_tokens == 42
    assert summary.output_tokens == 8


# ─── TTFT distribution ─────────────────────────────────────────────────


def test_ttft_only_over_streaming_entries() -> None:
    streaming = _entry(
        stream_chunks=[
            StreamChunk(data={"delta": "a"}, t_offset_ms=120),
            StreamChunk(data={"delta": "b"}, t_offset_ms=200),
        ]
    )
    non_streaming = _entry(response_body={"text": "static"})
    summary = aggregate([streaming, non_streaming])
    assert summary.ttft.count == 1
    assert summary.ttft.min_ms == 120
    assert summary.ttft.max_ms == 120


def test_ttft_first_chunk_offset_is_ttft() -> None:
    chunks = [
        StreamChunk(data={"delta": "a"}, t_offset_ms=42),
        StreamChunk(data={"delta": "b"}, t_offset_ms=200),
    ]
    summary = aggregate([_entry(stream_chunks=chunks)])
    assert summary.ttft.min_ms == 42
    assert summary.ttft.max_ms == 42


def test_ttft_empty_stream_chunks_skipped() -> None:
    # stream_chunks = [] → not a true streaming entry → skip
    entry = _entry(stream_chunks=[])
    summary = aggregate([entry])
    assert summary.ttft.count == 0


def test_ttft_distribution_percentiles_on_fixed_sample() -> None:
    # 10 samples, TTFTs of 10, 20, …, 100ms. Inclusive quantiles place:
    #   p50 = 55.0  (midpoint of 50 and 60)
    #   p95 = 95.5  (midpoint of 90 and 100, weighted)
    #   p99 = 99.1
    samples = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    entries = [
        _entry(stream_chunks=[StreamChunk(data={"delta": "x"}, t_offset_ms=ms)]) for ms in samples
    ]
    summary = aggregate(entries)
    t = summary.ttft
    assert t.count == 10
    assert t.min_ms == 10
    assert t.max_ms == 100
    assert t.p50_ms == 55.0
    assert t.p95_ms is not None
    assert t.p99_ms is not None
    # Tight assertions on rounded values — guards against silent reordering.
    assert round(t.p95_ms, 1) == 95.5
    assert round(t.p99_ms, 1) == 99.1


def test_ttft_too_few_samples_returns_none_for_higher_percentiles() -> None:
    # 3 samples → p50 ok, p95/p99 set to None to avoid pretending we know.
    entries = [
        _entry(stream_chunks=[StreamChunk(data={"d": "x"}, t_offset_ms=100)]),
        _entry(stream_chunks=[StreamChunk(data={"d": "x"}, t_offset_ms=200)]),
        _entry(stream_chunks=[StreamChunk(data={"d": "x"}, t_offset_ms=300)]),
    ]
    summary = aggregate(entries)
    t = summary.ttft
    assert t.count == 3
    assert t.min_ms == 100
    assert t.max_ms == 300
    assert t.p50_ms is not None
    assert t.p95_ms is None
    assert t.p99_ms is None


def test_ttft_single_sample_has_min_max_but_no_percentiles() -> None:
    entries = [
        _entry(stream_chunks=[StreamChunk(data={"d": "x"}, t_offset_ms=42)]),
    ]
    summary = aggregate(entries)
    t = summary.ttft
    assert t.count == 1
    assert t.min_ms == 42
    assert t.max_ms == 42
    assert t.p50_ms is None
    assert t.p95_ms is None
    assert t.p99_ms is None


# ─── Single-pass sanity (iterator consumed once) ───────────────────────


def test_aggregate_consumes_iterator_exactly_once() -> None:
    calls = {"n": 0}

    def gen() -> object:
        for ms in (10, 20, 30, 40):
            calls["n"] += 1
            yield _entry(stream_chunks=[StreamChunk(data={"d": "x"}, t_offset_ms=ms)])

    summary = aggregate(gen())  # type: ignore[arg-type]
    assert summary.total == 4
    assert calls["n"] == 4  # Each entry visited exactly once.
