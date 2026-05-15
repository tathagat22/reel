"""Sprint 6.1-6.3 — ``reel ui`` CLI wiring.

We patch the inspector's ``serve`` so the test never tries to bind a port,
and just assert that the right arguments make it through the Typer layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from reel.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_serve(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Patch the symbol the CLI command imports — not the source module — so
    the substitution is in scope for the duration of the test."""
    mock = MagicMock()
    monkeypatch.setattr("reel.cli.commands.ui.serve", mock)
    yield mock


def _last_call(mock: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    return mock.call_args.args, mock.call_args.kwargs


def test_ui_requires_cassette(runner: CliRunner) -> None:
    result = runner.invoke(app, ["ui"])
    assert result.exit_code != 0


def test_ui_missing_cassette_exits_2(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    result = runner.invoke(app, ["ui", "--cassette", str(missing)])
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_ui_invokes_serve_with_defaults(
    runner: CliRunner, mock_serve: MagicMock, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"
    cassette.write_text("")
    result = runner.invoke(app, ["ui", "--cassette", str(cassette)])
    assert result.exit_code == 0, result.stdout

    args, kwargs = _last_call(mock_serve)
    # The CLI passes the cassette as a positional Path, host/port as kwargs.
    assert args[0] == cassette
    assert kwargs.get("host") == "127.0.0.1"
    assert kwargs.get("port") == 7879


def test_ui_overrides_host_and_port(
    runner: CliRunner, mock_serve: MagicMock, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"
    cassette.write_text("")
    result = runner.invoke(
        app,
        ["ui", "--cassette", str(cassette), "--host", "0.0.0.0", "--port", "9090"],
    )
    assert result.exit_code == 0, result.stdout

    args, kwargs = _last_call(mock_serve)
    assert args[0] == cassette
    assert kwargs.get("host") == "0.0.0.0"
    assert kwargs.get("port") == 9090
