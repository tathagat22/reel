"""``reel stats`` — aggregate summary of a cassette.

Renders counts (total / per provider / per status class), token totals
(input / output / sum), and a TTFT distribution over streaming entries only.
Filtering is intentionally not part of stats — pipe through ``reel inspect``
when you want a subset; this command is for the at-a-glance summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.table import Table

from reel.analytics.stats import StatsSummary, aggregate
from reel.cassette.reader import CassetteReader

console = Console()

By = Literal["provider", "status", "summary"]


def run(
    cassette: Annotated[
        Path,
        typer.Option("--cassette", "-c", help="Cassette JSONL to summarize."),
    ],
    by: Annotated[
        str,
        typer.Option(
            "--by",
            help="Focus the output: 'provider', 'status', or 'summary' (default).",
        ),
    ] = "summary",
) -> None:
    """Summarize a cassette: counts, error rate, tokens, TTFT distribution."""
    if not cassette.exists():
        console.print(f"[bold red]error[/] cassette not found: {cassette}")
        raise typer.Exit(code=2)

    if by not in ("provider", "status", "summary"):
        console.print(f"[bold red]error[/] --by must be one of provider|status|summary, got {by!r}")
        raise typer.Exit(code=2)

    summary = aggregate(CassetteReader(cassette).iter_entries())
    _render(summary, cassette, by)


# ─── Rendering ─────────────────────────────────────────────────────────


def _render(summary: StatsSummary, cassette: Path, by: str) -> None:
    console.print(f"[bold magenta]reel stats[/] · [cyan]{cassette}[/]")

    if by == "provider":
        console.print(_provider_table(summary))
        return
    if by == "status":
        console.print(_status_table(summary))
        return

    # Default 'summary': counts + tokens + TTFT.
    console.print(_counts_table(summary))
    console.print(_tokens_table(summary))
    if summary.ttft.count > 0:
        console.print(_ttft_table(summary))
    else:
        console.print("[dim]no streaming entries — TTFT distribution skipped[/]")


def _counts_table(summary: StatsSummary) -> Table:
    table = Table(title="Counts", header_style="bold magenta", show_lines=False)
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("entries", str(summary.total))
    table.add_row("error rate", f"{summary.error_rate * 100:.1f}%")
    if summary.by_provider:
        table.add_row("by provider", _kv_inline(summary.by_provider))
    if summary.by_status_class:
        table.add_row("by status", _kv_inline(summary.by_status_class))
    return table


def _tokens_table(summary: StatsSummary) -> Table:
    table = Table(title="Tokens", header_style="bold magenta", show_lines=False)
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("input", f"{summary.input_tokens:,}")
    table.add_row("output", f"{summary.output_tokens:,}")
    table.add_row("total", f"{summary.total_tokens:,}")
    return table


def _ttft_table(summary: StatsSummary) -> Table:
    t = summary.ttft
    table = Table(title="TTFT (streaming)", header_style="bold magenta", show_lines=False)
    table.add_column("metric")
    table.add_column("ms", justify="right")
    table.add_row("samples", str(t.count))
    table.add_row("min", _fmt_ms(t.min_ms))
    table.add_row("p50", _fmt_ms(t.p50_ms))
    table.add_row("p95", _fmt_ms(t.p95_ms))
    table.add_row("p99", _fmt_ms(t.p99_ms))
    table.add_row("max", _fmt_ms(t.max_ms))
    return table


def _provider_table(summary: StatsSummary) -> Table:
    table = Table(title="By provider", header_style="bold magenta")
    table.add_column("provider")
    table.add_column("count", justify="right")
    for provider, count in sorted(summary.by_provider.items()):
        table.add_row(provider, str(count))
    if not summary.by_provider:
        table.add_row("(none)", "0")
    return table


def _status_table(summary: StatsSummary) -> Table:
    table = Table(title="By status class", header_style="bold magenta")
    table.add_column("class")
    table.add_column("count", justify="right")
    for klass, count in sorted(summary.by_status_class.items()):
        table.add_row(klass, str(count))
    if not summary.by_status_class:
        table.add_row("(none)", "0")
    return table


def _kv_inline(d: dict[str, int]) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(d.items()))


def _fmt_ms(value: int | float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}"
