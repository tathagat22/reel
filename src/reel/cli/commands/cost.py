"""``reel cost`` — aggregate token spend in a cassette.

Loads pricing from a bundled JSON table (or a user override) and prints a
``rich`` table grouped by model (default), provider, or rolled up into a
single total. Footer row shows the grand total across every priced entry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from reel.analytics.cost import CostRow, CostSummary, load_pricing, total_cost
from reel.cassette.reader import CassetteReader

console = Console()


def run(
    cassette: Annotated[
        Path,
        typer.Option("--cassette", "-c", help="Cassette JSONL to price."),
    ],
    pricing: Annotated[
        Path | None,
        typer.Option(
            "--pricing",
            help="Override the bundled pricing table (USD per 1M tokens).",
        ),
    ] = None,
    by: Annotated[
        str,
        typer.Option(
            "--by",
            help="Group rows by 'provider', 'model' (default), or 'total'.",
        ),
    ] = "model",
) -> None:
    """Sum the token cost of every priced entry in the cassette."""
    if not cassette.exists():
        console.print(f"[bold red]error[/] cassette not found: {cassette}")
        raise typer.Exit(code=2)

    if by not in ("provider", "model", "total"):
        console.print(f"[bold red]error[/] --by must be 'provider' | 'model' | 'total', got {by!r}")
        raise typer.Exit(code=2)

    table_data = total_cost(
        CassetteReader(cassette).iter_entries(),
        load_pricing(pricing),
        by=by,
    )

    _render(table_data, cassette=cassette, by=by)


# ─── Rendering ─────────────────────────────────────────────────────────


def _render(summary: CostSummary, *, cassette: Path, by: str) -> None:
    scope_label = {"provider": "provider", "model": "provider/model", "total": "scope"}[by]
    table = Table(
        title=f"reel cost · [cyan]{cassette}[/]",
        header_style="bold magenta",
        show_lines=False,
        show_footer=True,
    )
    table.add_column(scope_label, style="bold", footer="[bold]TOTAL[/]")
    table.add_column(
        "input tokens",
        justify="right",
        footer=f"[bold]{summary.total.input_tokens:,}[/]",
    )
    table.add_column(
        "output tokens",
        justify="right",
        footer=f"[bold]{summary.total.output_tokens:,}[/]",
    )
    table.add_column(
        "input $",
        justify="right",
        footer=f"[bold]{_fmt_usd(summary.total.input_usd)}[/]",
    )
    table.add_column(
        "output $",
        justify="right",
        footer=f"[bold]{_fmt_usd(summary.total.output_usd)}[/]",
    )
    table.add_column(
        "total $",
        justify="right",
        footer=f"[bold]{_fmt_usd(summary.total.total_usd)}[/]",
    )

    if not summary.rows:
        console.print(table)
        console.print("[dim]no entries with usage info found[/]")
        return

    for row in summary.rows:
        table.add_row(*_row_cells(row))

    console.print(table)

    if summary.unpriced_models:
        joined = ", ".join(f"{p}/{m}" for p, m in summary.unpriced_models)
        console.print(f"[yellow]N/A pricing for:[/] {joined}")


def _row_cells(row: CostRow) -> tuple[str, str, str, str, str, str]:
    if row.priced:
        return (
            row.scope,
            f"{row.input_tokens:,}",
            f"{row.output_tokens:,}",
            _fmt_usd(row.input_usd),
            _fmt_usd(row.output_usd),
            _fmt_usd(row.total_usd),
        )
    return (
        row.scope,
        f"{row.input_tokens:,}",
        f"{row.output_tokens:,}",
        "[dim]N/A[/]",
        "[dim]N/A[/]",
        "[dim]N/A[/]",
    )


def _fmt_usd(value: float) -> str:
    """Four decimals for sub-dollar amounts, two otherwise — keeps small entries readable."""
    if value == 0.0:
        return "$0.00"
    if value < 1.0:
        return f"${value:.4f}"
    return f"${value:,.2f}"
