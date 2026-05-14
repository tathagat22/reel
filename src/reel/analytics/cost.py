"""Cost analytics — pure functions over :class:`CassetteEntry` sequences.

Token shapes vary by provider:

* **OpenAI** — ``usage.prompt_tokens`` / ``usage.completion_tokens``. For
  streaming, usage is only present in the final SSE event when the request
  set ``stream_options.include_usage=true``.
* **Anthropic** — ``usage.input_tokens`` / ``usage.output_tokens``. For
  streaming, usage is delivered on a ``message_delta`` event near the end.
* **Gemini** — ``usageMetadata.promptTokenCount`` /
  ``usageMetadata.candidatesTokenCount``. For streaming, the final chunk
  carries the cumulative ``usageMetadata``.

Pricing is loaded from a bundled JSON table (USD per 1M tokens, split into
``input`` and ``output``). Callers may override with a custom path. Unknown
``(provider, model)`` pairs are skipped from the dollar columns but still
counted toward token totals so users can see what's uncovered.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from reel.cassette.schema import CassetteEntry, StreamChunk

_DEFAULT_PRICING_PATH = Path(__file__).parent / "pricing.json"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-1M-token USD prices for one model."""

    input: float
    output: float


def _empty_pricing_table() -> dict[str, dict[str, ModelPrice]]:
    return {}


@dataclass(frozen=True, slots=True)
class Pricing:
    """In-memory pricing table: ``provider -> model -> ModelPrice``.

    Constructed by :func:`load_pricing`; immutable so it's safe to share
    across aggregations.
    """

    table: dict[str, dict[str, ModelPrice]] = field(default_factory=_empty_pricing_table)

    def lookup(self, provider: str, model: str) -> ModelPrice | None:
        """Return the price for ``(provider, model)`` or ``None`` if absent."""
        return self.table.get(provider, {}).get(model)


@dataclass(frozen=True, slots=True)
class EntryCost:
    """Per-entry cost breakdown."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    input_usd: float
    """``0.0`` when no pricing entry exists for ``(provider, model)``."""
    output_usd: float
    """``0.0`` when no pricing entry exists for ``(provider, model)``."""
    priced: bool
    """``True`` when a pricing row matched; ``False`` for unknown models."""

    @property
    def total_usd(self) -> float:
        return self.input_usd + self.output_usd


@dataclass(frozen=True, slots=True)
class CostRow:
    """Aggregated cost for one scope (provider, model, or grand total)."""

    scope: str
    input_tokens: int
    output_tokens: int
    input_usd: float
    output_usd: float
    priced: bool
    """``False`` when *every* contributing entry was un-priced (no pricing row)."""

    @property
    def total_usd(self) -> float:
        return self.input_usd + self.output_usd


@dataclass(frozen=True, slots=True)
class CostSummary:
    """Result of :func:`total_cost` — per-key rows plus a grand total."""

    rows: list[CostRow]
    total: CostRow
    unpriced_models: list[tuple[str, str]]
    """``(provider, model)`` pairs we saw but had no pricing for."""


# ─── Loading ───────────────────────────────────────────────────────────


def load_pricing(path: Path | None = None) -> Pricing:
    """Load a pricing table from ``path`` or the bundled default.

    The JSON shape is ``{provider: {model: {"input": float, "output": float}}}``.
    Numbers are USD per 1,000,000 tokens.
    """
    src = path if path is not None else _DEFAULT_PRICING_PATH
    raw: Any = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"pricing file {src} must be a JSON object at the top level")
    table: dict[str, dict[str, ModelPrice]] = {}
    for provider, models in cast(dict[str, Any], raw).items():
        if not isinstance(models, dict):
            raise ValueError(f"pricing[{provider!r}] must be an object of model -> price")
        bucket: dict[str, ModelPrice] = {}
        for model, prices in cast(dict[str, Any], models).items():
            if not isinstance(prices, dict):
                raise ValueError(
                    f"pricing[{provider!r}][{model!r}] must be an object with input/output"
                )
            p = cast(dict[str, Any], prices)
            inp = p.get("input")
            out = p.get("output")
            if not isinstance(inp, (int, float)) or not isinstance(out, (int, float)):
                raise ValueError(f"pricing[{provider!r}][{model!r}] needs numeric input and output")
            bucket[model] = ModelPrice(input=float(inp), output=float(out))
        table[provider] = bucket
    return Pricing(table=table)


# ─── Per-entry extraction ──────────────────────────────────────────────


def entry_cost(entry: CassetteEntry, pricing: Pricing) -> EntryCost | None:
    """Compute the cost for one entry, or ``None`` if no usage info is present.

    Looks at the response body first, then the final stream chunks (which is
    where OpenAI / Anthropic / Gemini surface usage on streamed responses).
    """
    model = _request_model(entry)
    if model is None:
        return None

    tokens = _extract_tokens(entry)
    if tokens is None:
        return None
    input_tokens, output_tokens = tokens

    price = pricing.lookup(entry.provider, model)
    if price is None:
        return EntryCost(
            provider=entry.provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_usd=0.0,
            output_usd=0.0,
            priced=False,
        )

    return EntryCost(
        provider=entry.provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_usd=input_tokens * price.input / 1_000_000,
        output_usd=output_tokens * price.output / 1_000_000,
        priced=True,
    )


# ─── Aggregation ───────────────────────────────────────────────────────


def total_cost(
    entries: Iterable[CassetteEntry],
    pricing: Pricing,
    by: str = "model",
) -> CostSummary:
    """Aggregate tokens and USD across ``entries``.

    ``by`` controls grouping:

    * ``"model"`` — one row per ``(provider, model)`` pair (default).
    * ``"provider"`` — one row per provider.
    * ``"total"`` — a single grand-total row (still echoed in ``total``).

    Single pass; no intermediate lists. Entries without usage info are
    skipped silently.
    """
    if by not in ("provider", "model", "total"):
        raise ValueError(f"by must be 'provider' | 'model' | 'total', got {by!r}")

    # Accumulator: scope-key -> [in_tok, out_tok, in_usd, out_usd, any_priced]
    bucket: dict[str, list[float]] = {}
    total_acc: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0]
    unpriced: dict[tuple[str, str], None] = {}

    for entry in entries:
        cost = entry_cost(entry, pricing)
        if cost is None:
            continue

        key = _scope_key(cost, by)
        slot = bucket.get(key)
        if slot is None:
            slot = [0.0, 0.0, 0.0, 0.0, 0.0]
            bucket[key] = slot
        slot[0] += cost.input_tokens
        slot[1] += cost.output_tokens
        slot[2] += cost.input_usd
        slot[3] += cost.output_usd
        if cost.priced:
            slot[4] = 1.0

        total_acc[0] += cost.input_tokens
        total_acc[1] += cost.output_tokens
        total_acc[2] += cost.input_usd
        total_acc[3] += cost.output_usd
        if cost.priced:
            total_acc[4] = 1.0

        if not cost.priced:
            unpriced[(cost.provider, cost.model)] = None

    rows = [
        CostRow(
            scope=key,
            input_tokens=int(slot[0]),
            output_tokens=int(slot[1]),
            input_usd=slot[2],
            output_usd=slot[3],
            priced=bool(slot[4]),
        )
        for key, slot in bucket.items()
    ]
    rows.sort(key=lambda r: r.scope)

    total = CostRow(
        scope="TOTAL",
        input_tokens=int(total_acc[0]),
        output_tokens=int(total_acc[1]),
        input_usd=total_acc[2],
        output_usd=total_acc[3],
        priced=bool(total_acc[4]),
    )

    return CostSummary(rows=rows, total=total, unpriced_models=list(unpriced.keys()))


# ─── Helpers ───────────────────────────────────────────────────────────


def _scope_key(cost: EntryCost, by: str) -> str:
    if by == "provider":
        return cost.provider
    if by == "model":
        return f"{cost.provider}/{cost.model}"
    return "TOTAL"


def _request_model(entry: CassetteEntry) -> str | None:
    body = entry.request.body
    if isinstance(body, dict):
        model = cast(dict[str, Any], body).get("model")
        if isinstance(model, str):
            return model
    return None


def _extract_tokens(entry: CassetteEntry) -> tuple[int, int] | None:
    """Find ``(input_tokens, output_tokens)`` across all provider shapes.

    Searches the response body first; falls back to the tail of the stream
    chunks (last chunk that carries usage info). Returns ``None`` when no
    usage payload was captured.
    """
    body = entry.response.body
    if isinstance(body, dict):
        tokens = _tokens_from_dict(cast(dict[str, Any], body))
        if tokens is not None:
            return tokens

    chunks = entry.response.stream_chunks
    if chunks is not None:
        return _tokens_from_chunks(chunks)
    return None


def _tokens_from_chunks(chunks: list[StreamChunk]) -> tuple[int, int] | None:
    """Scan stream chunks from the end — usage rides on the final payload(s)."""
    for chunk in reversed(chunks):
        data = chunk.data
        if isinstance(data, dict):
            tokens = _tokens_from_dict(cast(dict[str, Any], data))
            if tokens is not None:
                return tokens
    return None


def _tokens_from_dict(d: dict[str, Any]) -> tuple[int, int] | None:
    """Try OpenAI / Anthropic / Gemini usage shapes in turn."""
    # OpenAI + Anthropic — flat ``usage`` object.
    usage = d.get("usage")
    if isinstance(usage, dict):
        u = cast(dict[str, Any], usage)
        inp = u.get("prompt_tokens")
        out = u.get("completion_tokens")
        if isinstance(inp, int) and isinstance(out, int):
            return inp, out
        inp = u.get("input_tokens")
        out = u.get("output_tokens")
        if isinstance(inp, int) and isinstance(out, int):
            return inp, out

    # Gemini — ``usageMetadata`` with promptTokenCount / candidatesTokenCount.
    meta = d.get("usageMetadata")
    if isinstance(meta, dict):
        m = cast(dict[str, Any], meta)
        inp = m.get("promptTokenCount")
        out = m.get("candidatesTokenCount")
        if isinstance(inp, int) and isinstance(out, int):
            return inp, out

    return None
