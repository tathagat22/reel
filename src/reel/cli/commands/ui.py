"""``reel ui`` — launch the local web cassette inspector.

A second small Starlette server, separate from the proxy, that serves an
HTMX UI for browsing a JSONL cassette. Defaults to ``:7879`` so it can run
alongside the proxy on ``:7878``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from reel import __version__
from reel.inspector.server import DEFAULT_HOST, DEFAULT_PORT, serve

console = Console()


def run(
    cassette: Annotated[
        Path,
        typer.Option("--cassette", "-c", help="Cassette JSONL to inspect."),
    ],
    host: Annotated[
        str,
        typer.Option("--host", help="Bind address for the inspector."),
    ] = DEFAULT_HOST,
    port: Annotated[
        int,
        typer.Option("--port", help="TCP port for the inspector."),
    ] = DEFAULT_PORT,
) -> None:
    """Launch the local web cassette inspector at http://host:port."""
    if not cassette.exists():
        console.print(f"[bold red]error[/] cassette not found: {cassette}")
        raise typer.Exit(code=2)

    console.print(f"[bold magenta]reel[/] [dim]{__version__}[/] · inspector")
    console.print(f"  listen   [cyan]http://{host}:{port}[/]")
    console.print(f"  cassette [cyan]{cassette}[/]")
    console.print("[dim]Open the URL in your browser to browse, filter, and inspect entries.[/]")
    serve(cassette, host=host, port=port)
