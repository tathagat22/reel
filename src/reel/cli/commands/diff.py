"""``reel diff`` — surface drift between two cassette files.

Pairs entries from the two cassettes by request fingerprint and renders a
single Rich table:

* green   — entry matched and bodies are equal
* yellow  — entry matched but content/status/model/tokens drifted
* red     — present on the left, missing on the right (removed)
* blue    — present on the right, missing on the left (added)

A count footer summarizes the four buckets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.table import Table

from reel.analytics.diff import Alignment, align_entries, compare_entries
from reel.cassette.reader import CassetteReader
from reel.cassette.schema import CassetteEntry

console = Console()


_KIND_STYLE: dict[str, str] = {
    "both": "green",
    "changed": "yellow",
    "left_only": "red",
    "right_only": "blue",
}


def run(
    left: Annotated[
        Path,
        typer.Option("--left", "-l", help="Left-hand cassette (the 'before')."),
    ],
    right: Annotated[
        Path,
        typer.Option("--right", "-r", help="Right-hand cassette (the 'after')."),
    ],
    show_bodies: Annotated[
        bool,
        typer.Option(
            "--show-bodies/--no-show-bodies",
            help="Show response-body snippets for entries whose bodies changed.",
        ),
    ] = True,
) -> None:
    """Compare two cassettes and report what drifted."""
    missing = [p for p in (left, right) if not p.exists()]
    if missing:
        for p in missing:
            console.print(f"[bold red]error[/] cassette not found: {p}")
        raise typer.Exit(code=2)

    left_entries = CassetteReader(left).load_all()
    right_entries = CassetteReader(right).load_all()

    alignments = align_entries(left_entries, right_entries)
    _render(alignments, left, right, show_bodies=show_bodies)


# ─── Rendering ─────────────────────────────────────────────────────────


def _render(
    alignments: list[Alignment],
    left: Path,
    right: Path,
    *,
    show_bodies: bool,
) -> None:
    table = Table(
        title=f"reel diff · [cyan]{left}[/] ↔ [cyan]{right}[/]",
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("#", style="dim", justify="right")
    table.add_column("status")
    table.add_column("model")
    table.add_column("Δ tokens", justify="right")
    table.add_column("summary")

    counts = {"both": 0, "changed": 0, "left_only": 0, "right_only": 0}
    for i, alignment in enumerate(alignments, start=1):
        counts[alignment.kind] += 1
        style = _KIND_STYLE[alignment.kind]
        status_cell, model_cell, tokens_cell, summary_cell = _cells(
            alignment, show_bodies=show_bodies
        )
        table.add_row(
            f"[{style}]{i}[/]",
            status_cell,
            model_cell,
            tokens_cell,
            summary_cell,
        )

    console.print(table)
    console.print(
        "[dim]"
        f"both={counts['both']}  "
        f"[yellow]changed={counts['changed']}[/]  "
        f"[red]left-only={counts['left_only']}[/]  "
        f"[blue]right-only={counts['right_only']}[/]"
        "[/]"
    )


def _cells(alignment: Alignment, *, show_bodies: bool) -> tuple[str, str, str, str]:
    if alignment.kind == "left_only":
        assert alignment.left is not None
        return (
            f"[red]{alignment.left.response.status}[/]",
            f"[red]{_model_name(alignment.left) or '-'}[/]",
            "-",
            "[red]left-only (removed)[/]",
        )
    if alignment.kind == "right_only":
        assert alignment.right is not None
        return (
            f"[blue]{alignment.right.response.status}[/]",
            f"[blue]{_model_name(alignment.right) or '-'}[/]",
            "-",
            "[blue]right-only (added)[/]",
        )

    # paired: both / changed
    assert alignment.left is not None and alignment.right is not None
    diff = compare_entries(alignment.left, alignment.right)
    status_cell = _status_cell(alignment.left.response.status, alignment.right.response.status)
    model_cell = _model_cell(_model_name(alignment.left), _model_name(alignment.right))
    tokens_cell = _tokens_cell(diff.tokens_delta)

    if alignment.kind == "both":
        summary = "[green]unchanged[/]"
    else:
        summary_lines = list(diff.lines)
        if show_bodies and diff.body_changed:
            snippet = _body_snippet(alignment.left, alignment.right)
            if snippet:
                summary_lines.append(snippet)
        summary = (
            "[yellow]" + "; ".join(summary_lines) + "[/]" if summary_lines else "[yellow]changed[/]"
        )

    return status_cell, model_cell, tokens_cell, summary


def _status_cell(left_status: int, right_status: int) -> str:
    if left_status == right_status:
        return str(left_status)
    return f"[yellow]{left_status} → {right_status}[/]"


def _model_cell(left_model: str | None, right_model: str | None) -> str:
    if left_model == right_model:
        return left_model or "-"
    return f"[yellow]{left_model or '-'} → {right_model or '-'}[/]"


def _tokens_cell(delta: int | None) -> str:
    if delta is None:
        return "-"
    if delta == 0:
        return "0"
    sign = "+" if delta > 0 else ""
    style = "yellow" if delta != 0 else ""
    return f"[{style}]{sign}{delta}[/]" if style else f"{sign}{delta}"


def _model_name(entry: CassetteEntry) -> str | None:
    body = entry.request.body
    if isinstance(body, dict):
        model = cast(dict[str, Any], body).get("model")
        if isinstance(model, str):
            return model
    return None


def _body_snippet(left: CassetteEntry, right: CassetteEntry) -> str:
    """Return ``"L: <left>  R: <right>"`` (each truncated) for a body diff."""
    left_s = _short(_serialize_body(left))
    right_s = _short(_serialize_body(right))
    return f"L: {left_s}  R: {right_s}"


def _serialize_body(entry: CassetteEntry) -> str:
    if entry.response.stream_chunks is not None:
        return f"<{len(entry.response.stream_chunks)} streamed chunks>"
    body = entry.response.body
    if body is None:
        return "(empty)"
    if isinstance(body, dict | list):
        return json.dumps(body, ensure_ascii=False)
    return str(body)


def _short(s: str, n: int = 40) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"
