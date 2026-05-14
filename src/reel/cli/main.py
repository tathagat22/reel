"""Reel CLI entry point.

Wired in pyproject under ``[project.scripts]`` as
``reel = "reel.cli.main:app"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from reel import __version__
from reel.proxy.config import DEFAULT_HOST, DEFAULT_OPENAI_UPSTREAM, DEFAULT_PORT, ProxyConfig
from reel.proxy.server import serve

app = typer.Typer(
    name="reel",
    help="VCR for LLM APIs — record and replay OpenAI/Anthropic/Gemini calls.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


# ─── Shared option types ───────────────────────────────────────────────

HostOpt = Annotated[
    str,
    typer.Option("--host", "-h", help="Bind address for the proxy."),
]
PortOpt = Annotated[
    int,
    typer.Option("--port", "-p", help="TCP port for the proxy."),
]
CassetteOpt = Annotated[
    Path,
    typer.Option(
        "--cassette",
        "-c",
        help="Path to the JSONL cassette file (read for replay, append for record).",
    ),
]
OptionalCassetteOpt = Annotated[
    Path | None,
    typer.Option(
        "--cassette",
        "-c",
        help="Path to the JSONL cassette file (auto-recorded on first miss).",
    ),
]
UpstreamOpt = Annotated[
    str,
    typer.Option("--upstream", help="OpenAI-compatible upstream base URL."),
]
TimingOpt = Annotated[
    str,
    typer.Option(
        "--timing",
        help="Streamed replay pacing: 'realtime' (default), 'fast', 'slow=<N>', or a bare multiplier (1.0=realtime, 0=fast).",
    ),
]


def parse_timing(value: str) -> float:
    """Translate a CLI ``--timing`` value to a sleep-multiplier float."""
    v = value.strip().lower()
    if v == "realtime":
        return 1.0
    if v == "fast":
        return 0.0
    if v.startswith("slow="):
        try:
            n = float(v[5:])
        except ValueError as exc:
            raise typer.BadParameter(
                f"--timing slow=<N>: expected a number, got {value[5:]!r}"
            ) from exc
        if n <= 0:
            raise typer.BadParameter("--timing slow=<N>: multiplier must be > 0")
        return n
    try:
        return float(v)
    except ValueError as exc:
        raise typer.BadParameter(
            "--timing must be 'realtime', 'fast', 'slow=<N>', or a bare number"
        ) from exc


def _print_banner(mode: str, cassette: Path | None, host: str, port: int, upstream: str) -> None:
    console.print(f"[bold magenta]reel[/] [dim]{__version__}[/] · mode=[bold]{mode}[/]")
    console.print(f"  listen   [cyan]http://{host}:{port}[/]")
    console.print(f"  upstream [cyan]{upstream}[/]")
    console.print(f"  cassette [cyan]{cassette or '(none)'}[/]")
    console.print("[dim]Point your SDK at the proxy and start making LLM calls.[/]")


def _build_config(
    mode: str,
    host: str,
    port: int,
    cassette: Path | None,
    upstream: str,
    timing_multiplier: float = 1.0,
) -> ProxyConfig:
    return ProxyConfig(
        host=host,
        port=port,
        mode=mode,  # type: ignore[arg-type]
        cassette_path=str(cassette) if cassette is not None else None,
        openai_upstream=upstream,
        replay_timing_multiplier=timing_multiplier,
    )


# ─── Commands ──────────────────────────────────────────────────────────


@app.command()
def record(
    cassette: CassetteOpt,
    host: HostOpt = DEFAULT_HOST,
    port: PortOpt = DEFAULT_PORT,
    upstream: UpstreamOpt = DEFAULT_OPENAI_UPSTREAM,
) -> None:
    """Forward every request upstream and capture it into the cassette."""
    cfg = _build_config("record", host, port, cassette, upstream)
    _print_banner("record", cassette, host, port, upstream)
    serve(cfg)


@app.command()
def replay(
    cassette: CassetteOpt,
    host: HostOpt = DEFAULT_HOST,
    port: PortOpt = DEFAULT_PORT,
    upstream: UpstreamOpt = DEFAULT_OPENAI_UPSTREAM,
    timing: TimingOpt = "realtime",
) -> None:
    """Serve responses from the cassette only. 404 on miss; no network."""
    if not cassette.exists():
        console.print(f"[bold red]error[/] cassette not found: {cassette}")
        raise typer.Exit(code=2)
    multiplier = parse_timing(timing)
    cfg = _build_config("replay", host, port, cassette, upstream, timing_multiplier=multiplier)
    _print_banner("replay", cassette, host, port, upstream)
    serve(cfg)


@app.command()
def auto(
    cassette: CassetteOpt,
    host: HostOpt = DEFAULT_HOST,
    port: PortOpt = DEFAULT_PORT,
    upstream: UpstreamOpt = DEFAULT_OPENAI_UPSTREAM,
    timing: TimingOpt = "realtime",
) -> None:
    """Replay if cached, else record. The right default for local dev."""
    multiplier = parse_timing(timing)
    cfg = _build_config("auto", host, port, cassette, upstream, timing_multiplier=multiplier)
    _print_banner("auto", cassette, host, port, upstream)
    serve(cfg)


@app.command()
def version() -> None:
    """Print the installed Reel version."""
    typer.echo(f"reel {__version__}")


@app.command()
def doctor(
    cassette: OptionalCassetteOpt = None,
) -> None:
    """Sanity-check Reel setup. (Stub — full implementation lands in Sprint 5.)"""
    console.print(f"[bold magenta]reel[/] [dim]{__version__}[/] [yellow]doctor[/]")
    console.print(f"  cassette: [cyan]{cassette or '(none provided)'}[/]")
    if cassette is not None:
        console.print(
            f"    exists: [{'green' if cassette.exists() else 'red'}]{cassette.exists()}[/]"
        )
    console.print("[dim]Sprint 1.9 stub — full diagnostic check lands in Sprint 5.[/]")


if __name__ == "__main__":
    app()
