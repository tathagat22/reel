"""Sprint 5.3 — cost analytics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reel.analytics.cost import (
    EntryCost,
    Pricing,
    entry_cost,
    load_pricing,
    total_cost,
)
from reel.cassette.schema import (
    CassetteEntry,
    CassetteRequest,
    CassetteResponse,
    StreamChunk,
)
from reel.cassette.writer import generate_id, now_iso

# ─── Fixtures ──────────────────────────────────────────────────────────


def _entry(
    *,
    provider: str = "openai",
    model: str = "gpt-5",
    response_body: dict[str, object] | None = None,
    stream_chunks: list[StreamChunk] | None = None,
    request_body: dict[str, object] | None = None,
) -> CassetteEntry:
    body: dict[str, object] = request_body or {"model": model, "messages": []}
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(method="POST", path="/x", fingerprint="sha256:x", body=body),
        response=CassetteResponse(
            status=200,
            headers={},
            body=response_body if stream_chunks is None else None,
            stream_chunks=stream_chunks,
        ),
    )


@pytest.fixture
def pricing() -> Pricing:
    return load_pricing()


# ─── load_pricing ──────────────────────────────────────────────────────


def test_load_default_pricing_has_expected_providers(pricing: Pricing) -> None:
    assert "openai" in pricing.table
    assert "anthropic" in pricing.table
    assert "gemini" in pricing.table


def test_load_default_pricing_lookup_returns_immutable_modelprice(pricing: Pricing) -> None:
    mp = pricing.lookup("openai", "gpt-5")
    assert mp is not None
    assert mp.input == 5.00
    assert mp.output == 15.00
    with pytest.raises(AttributeError):  # frozen dataclass
        mp.input = 999.0  # type: ignore[misc]


def test_load_pricing_from_custom_path(tmp_path: Path) -> None:
    p = tmp_path / "custom.json"
    p.write_text(
        json.dumps({"acme": {"laser-1": {"input": 1.0, "output": 2.0}}}),
        encoding="utf-8",
    )
    pricing = load_pricing(p)
    mp = pricing.lookup("acme", "laser-1")
    assert mp is not None
    assert mp.output == 2.0


def test_load_pricing_rejects_non_object_top_level(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_pricing(p)


def test_load_pricing_rejects_non_numeric_prices(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps({"openai": {"x": {"input": "free", "output": 0.0}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="numeric input and output"):
        load_pricing(p)


# ─── entry_cost — token shape extraction ───────────────────────────────


def test_entry_cost_openai_shape(pricing: Pricing) -> None:
    e = _entry(
        response_body={"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 2_000_000}}
    )
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.input_tokens == 1_000_000
    assert cost.output_tokens == 2_000_000
    # gpt-5: $5/1M in, $15/1M out → $5 + $30 = $35
    assert cost.input_usd == pytest.approx(5.0)
    assert cost.output_usd == pytest.approx(30.0)
    assert cost.total_usd == pytest.approx(35.0)
    assert cost.priced is True


def test_entry_cost_anthropic_shape(pricing: Pricing) -> None:
    e = _entry(
        provider="anthropic",
        model="claude-sonnet-4-6",
        response_body={"usage": {"input_tokens": 1_000_000, "output_tokens": 500_000}},
    )
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.input_tokens == 1_000_000
    assert cost.output_tokens == 500_000
    # claude-sonnet-4-6: $3/1M in, $15/1M out
    assert cost.input_usd == pytest.approx(3.0)
    assert cost.output_usd == pytest.approx(7.5)


def test_entry_cost_gemini_shape(pricing: Pricing) -> None:
    e = _entry(
        provider="gemini",
        model="gemini-1.5-flash",
        response_body={
            "usageMetadata": {
                "promptTokenCount": 1_000_000,
                "candidatesTokenCount": 1_000_000,
            }
        },
    )
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.input_tokens == 1_000_000
    assert cost.output_tokens == 1_000_000
    # gemini-1.5-flash: $0.075/1M in, $0.30/1M out
    assert cost.input_usd == pytest.approx(0.075)
    assert cost.output_usd == pytest.approx(0.30)


def test_entry_cost_returns_none_when_no_usage(pricing: Pricing) -> None:
    e = _entry(response_body={"id": "resp_1"})
    assert entry_cost(e, pricing) is None


def test_entry_cost_returns_none_when_no_model_in_request(pricing: Pricing) -> None:
    e = _entry(
        request_body={"messages": []},
        response_body={"usage": {"prompt_tokens": 10, "completion_tokens": 10}},
    )
    assert entry_cost(e, pricing) is None


def test_entry_cost_unknown_model_marks_unpriced(pricing: Pricing) -> None:
    e = _entry(
        model="future-mystery-model",
        response_body={"usage": {"prompt_tokens": 100, "completion_tokens": 200}},
    )
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.priced is False
    assert cost.input_tokens == 100
    assert cost.output_tokens == 200
    assert cost.input_usd == 0.0
    assert cost.output_usd == 0.0


# ─── entry_cost — streaming usage extraction ───────────────────────────


def test_entry_cost_openai_stream_usage_in_final_chunk(pricing: Pricing) -> None:
    chunks = [
        StreamChunk(data={"choices": [{"delta": {"content": "hi"}}]}, t_offset_ms=0),
        StreamChunk(
            data={
                "choices": [],
                "usage": {"prompt_tokens": 50, "completion_tokens": 100},
            },
            t_offset_ms=200,
        ),
        StreamChunk(data="[DONE]", t_offset_ms=210),
    ]
    e = _entry(stream_chunks=chunks)
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.input_tokens == 50
    assert cost.output_tokens == 100


def test_entry_cost_anthropic_stream_usage_in_message_delta(pricing: Pricing) -> None:
    chunks = [
        StreamChunk(
            data={"type": "message_start", "message": {"id": "m"}},
            t_offset_ms=0,
            event="message_start",
        ),
        StreamChunk(
            data={"type": "content_block_delta", "delta": {"text": "hi"}},
            t_offset_ms=10,
            event="content_block_delta",
        ),
        StreamChunk(
            data={
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"input_tokens": 12, "output_tokens": 34},
            },
            t_offset_ms=100,
            event="message_delta",
        ),
    ]
    e = _entry(provider="anthropic", model="claude-haiku-4-5", stream_chunks=chunks)
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.input_tokens == 12
    assert cost.output_tokens == 34


def test_entry_cost_gemini_stream_usage_in_final_chunk(pricing: Pricing) -> None:
    chunks = [
        StreamChunk(data={"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}, t_offset_ms=0),
        StreamChunk(
            data={
                "candidates": [{"finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 11},
            },
            t_offset_ms=200,
        ),
    ]
    e = _entry(provider="gemini", model="gemini-1.5-pro", stream_chunks=chunks)
    cost = entry_cost(e, pricing)
    assert cost is not None
    assert cost.input_tokens == 7
    assert cost.output_tokens == 11


def test_entry_cost_stream_without_usage_returns_none(pricing: Pricing) -> None:
    chunks = [
        StreamChunk(data={"choices": [{"delta": {"content": "hi"}}]}, t_offset_ms=0),
        StreamChunk(data="[DONE]", t_offset_ms=10),
    ]
    assert entry_cost(_entry(stream_chunks=chunks), pricing) is None


# ─── total_cost — aggregation ──────────────────────────────────────────


def test_total_cost_aggregates_by_model(pricing: Pricing) -> None:
    entries = [
        _entry(
            response_body={"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}},
        ),
        _entry(
            response_body={"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}},
        ),
        _entry(
            model="gpt-4o-mini",
            response_body={"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}},
        ),
    ]
    summary = total_cost(entries, pricing, by="model")

    keys = {r.scope: r for r in summary.rows}
    assert "openai/gpt-5" in keys
    assert "openai/gpt-4o-mini" in keys

    gpt5 = keys["openai/gpt-5"]
    assert gpt5.input_tokens == 2_000_000
    assert gpt5.input_usd == pytest.approx(10.0)

    mini = keys["openai/gpt-4o-mini"]
    assert mini.input_usd == pytest.approx(0.15)
    assert mini.output_usd == pytest.approx(0.60)

    # Grand total
    assert summary.total.input_tokens == 3_000_000
    assert summary.total.output_tokens == 1_000_000
    assert summary.total.input_usd == pytest.approx(10.15)
    assert summary.total.output_usd == pytest.approx(0.60)


def test_total_cost_aggregates_by_provider(pricing: Pricing) -> None:
    entries = [
        _entry(response_body={"usage": {"prompt_tokens": 100, "completion_tokens": 0}}),
        _entry(
            model="gpt-4o",
            response_body={"usage": {"prompt_tokens": 100, "completion_tokens": 0}},
        ),
        _entry(
            provider="anthropic",
            model="claude-haiku-4-5",
            response_body={"usage": {"input_tokens": 100, "output_tokens": 0}},
        ),
    ]
    summary = total_cost(entries, pricing, by="provider")
    keys = {r.scope: r for r in summary.rows}
    assert set(keys) == {"openai", "anthropic"}
    assert keys["openai"].input_tokens == 200
    assert keys["anthropic"].input_tokens == 100


def test_total_cost_by_total_single_row(pricing: Pricing) -> None:
    entries = [
        _entry(response_body={"usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
        _entry(
            provider="gemini",
            model="gemini-1.5-pro",
            response_body={"usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 30}},
        ),
    ]
    summary = total_cost(entries, pricing, by="total")
    assert len(summary.rows) == 1
    assert summary.rows[0].scope == "TOTAL"
    assert summary.rows[0].input_tokens == 30
    assert summary.rows[0].output_tokens == 35


def test_total_cost_skips_entries_without_usage(pricing: Pricing) -> None:
    entries = [
        _entry(response_body={"id": "no-usage"}),
        _entry(response_body={"usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
    ]
    summary = total_cost(entries, pricing, by="model")
    assert len(summary.rows) == 1
    assert summary.total.input_tokens == 10
    assert summary.total.output_tokens == 5


def test_total_cost_tracks_unpriced_models(pricing: Pricing) -> None:
    entries = [
        _entry(
            model="mystery-x",
            response_body={"usage": {"prompt_tokens": 100, "completion_tokens": 50}},
        ),
    ]
    summary = total_cost(entries, pricing, by="model")
    assert summary.unpriced_models == [("openai", "mystery-x")]
    assert summary.rows[0].priced is False
    assert summary.rows[0].input_usd == 0.0


def test_total_cost_rejects_invalid_by() -> None:
    pricing = Pricing()
    with pytest.raises(ValueError, match="provider"):
        total_cost([], pricing, by="garbage")


def test_total_cost_empty_input_returns_empty_summary(pricing: Pricing) -> None:
    summary = total_cost([], pricing, by="model")
    assert summary.rows == []
    assert summary.total.input_tokens == 0
    assert summary.total.output_tokens == 0
    assert summary.total.input_usd == 0.0


def test_entry_cost_is_immutable() -> None:
    cost = EntryCost(
        provider="openai",
        model="gpt-5",
        input_tokens=10,
        output_tokens=20,
        input_usd=0.0,
        output_usd=0.0,
        priced=True,
    )
    with pytest.raises(AttributeError):
        cost.input_tokens = 999  # type: ignore[misc]
