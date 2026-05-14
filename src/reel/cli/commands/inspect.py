"""``reel inspect`` — scannable view of a cassette's entries.

Filters compose: any combination of ``--provider``, ``--model``, ``--status``,
``--has-tool-call``, ``--regex``, ``--limit`` narrows the set. Default
rendering is a compact table; ``--verbose`` prints each entry in full.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.table import Table

from reel.analytics.filters import FilterSpec, apply
from reel.cassette.reader import CassetteReader
from reel.cassette.schema import CassetteEntry

console = Console()


def run(
    cassette: Annotated[
        Path,
        typer.Option("--cassette", "-c", help="Cassette JSONL to inspect."),
    ],
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Match exact provider: openai|anthropic|gemini."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Case-insensitive substring of the request body's `model`."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status", help="Response status: exact (`429`) or class (`2xx`/`4xx`/`5xx`)."
        ),
    ] = None,
    has_tool_call: Annotated[
        bool | None,
        typer.Option("--has-tool-call/--no-tool-call", help="Only entries that involve tools."),
    ] = None,
    regex: Annotated[
        str | None,
        typer.Option("--regex", help="Python regex applied to the JSON-serialized entry."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Stop after the first N matching entries."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print each entry's full body (instead of a table)."),
    ] = False,
) -> None:
    """Display a cassette's entries, filtered to your liking."""
    if not cassette.exists():
        console.print(f"[bold red]error[/] cassette not found: {cassette}")
        raise typer.Exit(code=2)

    spec = FilterSpec(
        provider=provider,
        model=model,
        status=status,
        has_tool_call=has_tool_call,
        regex=re.compile(regex) if regex else None,
        limit=limit,
    )

    entries = apply(spec, CassetteReader(cassette).iter_entries())

    if verbose:
        _render_verbose(entries, cassette)
    else:
        _render_table(entries, cassette)


# ─── Rendering ─────────────────────────────────────────────────────────


def _render_table(entries: object, cassette: Path) -> None:
    table = Table(
        title=f"reel inspect · [cyan]{cassette}[/]",
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("#", style="dim", justify="right")
    table.add_column("ts", style="dim")
    table.add_column("provider")
    table.add_column("method")
    table.add_column("path")
    table.add_column("model")
    table.add_column("status", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("body")

    matched = 0
    for i, entry in enumerate(cast(Any, entries), start=1):
        table.add_row(
            str(i),
            _short_ts(entry.ts),
            entry.provider,
            entry.request.method,
            _truncate(entry.request.path, 28),
            _truncate(_model_name(entry) or "-", 18),
            _status_cell(entry.response.status),
            _tokens_summary(entry),
            _body_summary(entry),
        )
        matched += 1

    console.print(table)
    console.print(f"[dim]{matched} entr{'y' if matched == 1 else 'ies'} matched[/]")


def _render_verbose(entries: object, cassette: Path) -> None:
    console.print(f"[bold magenta]reel inspect[/] · [cyan]{cassette}[/]\n")
    matched = 0
    for i, entry in enumerate(cast(Any, entries), start=1):
        console.rule(f"[bold]#{i}[/] · {entry.provider} · {entry.request.path}", style="dim")
        console.print(f"[dim]id:[/] {entry.id}    [dim]ts:[/] {entry.ts}")
        console.print(f"[dim]request body:[/]\n{_pretty(entry.request.body)}")
        console.print(
            f"[dim]response status:[/] {_status_cell(entry.response.status)}    "
            f"[dim]tokens:[/] {_tokens_summary(entry)}"
        )
        if entry.response.stream_chunks is not None:
            console.print(
                f"[dim]stream chunks:[/] {len(entry.response.stream_chunks)} "
                f"(captured over {entry.response.stream_chunks[-1].t_offset_ms}ms)"
            )
        else:
            console.print(f"[dim]response body:[/]\n{_pretty(entry.response.body)}")
        matched += 1
    console.print(f"\n[dim]{matched} entr{'y' if matched == 1 else 'ies'} matched[/]")


# ─── Cell formatters ───────────────────────────────────────────────────


def _short_ts(ts: str) -> str:
    """Trim ISO timestamps to ``HH:MM:SS`` for table density."""
    return ts.split("T", 1)[1].split("+", 1)[0] if "T" in ts else ts


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _model_name(entry: CassetteEntry) -> str | None:
    body = entry.request.body
    if isinstance(body, dict):
        model = cast(dict[str, Any], body).get("model")
        if isinstance(model, str):
            return model
    return None


def _status_cell(code: int) -> str:
    if 200 <= code < 300:
        return f"[green]{code}[/]"
    if 300 <= code < 400:
        return f"[yellow]{code}[/]"
    return f"[red]{code}[/]"


def _tokens_summary(entry: CassetteEntry) -> str:
    """Pull ``usage`` out of the response body if present (provider-specific shapes)."""
    body = entry.response.body
    if not isinstance(body, dict):
        return "-"
    d = cast(dict[str, Any], body)
    usage = d.get("usage")
    if not isinstance(usage, dict):
        return "-"
    u = cast(dict[str, Any], usage)
    # OpenAI: prompt_tokens / completion_tokens. Anthropic: input_tokens / output_tokens.
    inp = u.get("prompt_tokens") or u.get("input_tokens")
    out = u.get("completion_tokens") or u.get("output_tokens")
    if inp is None and out is None:
        return "-"
    return f"{inp or '?'}/{out or '?'}"


def _body_summary(entry: CassetteEntry) -> str:
    """One-line summary of the response body or stream."""
    if entry.response.stream_chunks is not None:
        n = len(entry.response.stream_chunks)
        return f"[dim]{n} streamed chunks[/]"
    body = entry.response.body
    if body is None:
        return "[dim](empty)[/]"
    if isinstance(body, dict):
        return _truncate(json.dumps(body, ensure_ascii=False), 60)
    return _truncate(str(body), 60)


def _pretty(value: Any) -> str:
    """Indented JSON for verbose mode; falls back to repr for non-JSON-y values."""
    if value is None:
        return "  (empty)"
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)
