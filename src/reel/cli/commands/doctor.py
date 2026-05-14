"""``reel doctor`` — sanity-check the local Reel setup.

Runs a handful of cheap, offline-by-default checks and renders a scannable
report. Designed to be the first thing a confused user reaches for ("why
isn't my proxy working?") before opening an issue.

Critical checks (any failure → exit 1):

* Python version >= 3.11
* If ``--cassette`` is set, the cassette's parent directory exists *and*
  is writable.

Informational checks (never fail the command):

* Port 7878 availability (yellow if already in use — a running proxy is
  often the cause).
* Upstream reachability for the three default providers.
* Whether ``sentence-transformers`` is importable (needed for the optional
  ``fuzzy`` match mode).
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.table import Table

from reel import __version__
from reel.proxy.config import (
    DEFAULT_ANTHROPIC_UPSTREAM,
    DEFAULT_GEMINI_UPSTREAM,
    DEFAULT_OPENAI_UPSTREAM,
    DEFAULT_PORT,
)

console = Console()

# ─── Status glyphs ─────────────────────────────────────────────────────

_PASS = "[green]✓[/]"  # ✓
_FAIL = "[red]✗[/]"  # ✗
_WARN = "[yellow]![/]"


# ─── Individual checks ─────────────────────────────────────────────────


def _check_python() -> tuple[str, str, bool]:
    """Verify the running interpreter is Python 3.11+.

    Returns ``(glyph, message, is_critical_failure)``.
    """
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return _PASS, f"python {version_str}", False
    return _FAIL, f"python {version_str} (need >= 3.11)", True


def _check_reel_version() -> tuple[str, str, bool]:
    """Report the installed Reel version. Never critical."""
    return _PASS, f"reel {__version__}", False


def _check_port(port: int = DEFAULT_PORT) -> tuple[str, str, bool]:
    """Try to bind 127.0.0.1:<port>. Already-in-use is informational, not fatal."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        return (
            _WARN,
            f"port {port} in use ({exc.strerror or exc}) — proxy may already be running",
            False,
        )
    finally:
        sock.close()
    return _PASS, f"port {port} available", False


def _check_cassette_path(cassette: Path) -> tuple[str, str, bool]:
    """Check the cassette's parent dir exists and is writable.

    Failure here is critical when the user explicitly passed ``--cassette``:
    they've told us where to write, and we can't.
    """
    parent = cassette.parent
    if not parent.exists():
        return _FAIL, f"cassette parent {parent} does not exist", True
    if not parent.is_dir():
        return _FAIL, f"cassette parent {parent} is not a directory", True
    # Use os.access rather than a real write probe — we don't want to
    # litter the user's filesystem just to verify writability.
    if not os.access(parent, os.W_OK):
        return _FAIL, f"cassette parent {parent} not writable", True
    return _PASS, f"cassette parent {parent} writable", False


def _check_upstream(name: str, url: str) -> tuple[str, str, bool]:
    """HEAD an upstream URL with a short timeout. Never critical.

    Most providers reject anonymous HEADs with 401/403/405 — that's a
    success signal here (TCP + TLS + the LLM provider's edge are alive).
    Only DNS / connection failures are reported as warnings.
    """
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.head(url)
    except httpx.HTTPError as exc:
        return _WARN, f"{name} ({url}) unreachable: {exc.__class__.__name__}", False
    return _PASS, f"{name} reachable ({resp.status_code})", False


def _check_fuzzy_extra() -> tuple[str, str, bool]:
    """Check whether the optional ``sentence-transformers`` dep is installed."""
    if importlib.util.find_spec("sentence_transformers") is not None:
        return _PASS, "fuzzy match deps (sentence-transformers) installed", False
    return (
        _WARN,
        r"fuzzy match deps (sentence-transformers) not installed — `uv pip install reel\[fuzzy]`",
        False,
    )


# ─── Entrypoint ────────────────────────────────────────────────────────


def run(
    cassette: Annotated[
        Path | None,
        typer.Option(
            "--cassette",
            "-c",
            help="If set, check write permissions on the parent dir.",
        ),
    ] = None,
    skip_network: Annotated[
        bool,
        typer.Option("--skip-network", help="Skip upstream reachability checks."),
    ] = False,
) -> None:
    """Diagnose a Reel install: Python, port, cassette path, upstreams, extras."""
    table = Table(
        title=f"[bold magenta]reel[/] doctor · [dim]{__version__}[/]",
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("", width=2)
    table.add_column("check", style="bold")
    table.add_column("detail")

    critical_failure = False

    for glyph, message, is_critical in (
        _check_python(),
        _check_reel_version(),
        _check_port(),
    ):
        table.add_row(glyph, _label(message), message)
        critical_failure = critical_failure or is_critical

    if cassette is not None:
        glyph, message, is_critical = _check_cassette_path(cassette)
        table.add_row(glyph, "cassette path", message)
        critical_failure = critical_failure or is_critical

    if not skip_network:
        for name, url in (
            ("openai", DEFAULT_OPENAI_UPSTREAM),
            ("anthropic", DEFAULT_ANTHROPIC_UPSTREAM),
            ("gemini", DEFAULT_GEMINI_UPSTREAM),
        ):
            glyph, message, _ = _check_upstream(name, url)
            table.add_row(glyph, f"upstream {name}", message)
    else:
        table.add_row(_WARN, "upstreams", "skipped (--skip-network)")

    glyph, message, _ = _check_fuzzy_extra()
    table.add_row(glyph, "fuzzy extras", message)

    console.print(table)
    if critical_failure:
        console.print("[bold red]doctor: one or more critical checks failed[/]")
        raise typer.Exit(code=1)
    console.print("[bold green]doctor: OK[/]")


# ─── Internals ─────────────────────────────────────────────────────────


def _label(message: str) -> str:
    """Pick a short label column from a human-readable check message.

    Keeps the rendered table tidy without forcing every helper to return
    a separate ``label`` string.
    """
    first_word = message.split(" ", 1)[0]
    return first_word
