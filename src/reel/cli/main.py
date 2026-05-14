"""Reel CLI entry point.

Wired in pyproject under `[project.scripts]` as `reel = "reel.cli.main:app"`.
Real commands (`record`, `replay`, `auto`, `inspect`, ...) land in Sprint 1+.
"""

from __future__ import annotations

import typer

from reel import __version__

app = typer.Typer(
    name="reel",
    help="VCR for LLM APIs — record and replay OpenAI/Anthropic/Gemini calls.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the installed Reel version."""
    typer.echo(f"reel {__version__}")


@app.command()
def doctor() -> None:
    """Placeholder. Real implementation in Sprint 5."""
    typer.echo("reel doctor — not implemented yet (Sprint 5)")


if __name__ == "__main__":
    app()
