"""Sprint 1.9 — CLI surface tests.

We exercise CLI parsing without actually starting uvicorn: every command is
patched so `serve()` becomes a recording stub. That keeps tests fast and
deterministic while still proving the wire-up between flags and config.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from reel.cli.main import app
from reel.proxy.config import ProxyConfig


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_serve(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Replace reel.cli.main.serve so we capture the config rather than launching uvicorn."""
    mock = MagicMock()
    monkeypatch.setattr("reel.cli.main.serve", mock)
    yield mock


def _last_config(mock: Any) -> ProxyConfig:
    cfg = mock.call_args.args[0]
    assert isinstance(cfg, ProxyConfig)
    return cfg


# ─── version + doctor ──────────────────────────────────────────────────


def test_version_command(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "reel " in result.stdout


def test_help_lists_all_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("record", "replay", "auto", "version", "doctor"):
        assert cmd in result.stdout


def test_doctor_with_missing_cassette(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    result = runner.invoke(app, ["doctor", "--cassette", str(missing)])
    assert result.exit_code == 0
    # Either "False" or just "exists: False" — be tolerant of formatting.
    assert "False" in result.stdout or "false" in result.stdout.lower()


# ─── record ────────────────────────────────────────────────────────────


def test_record_requires_cassette(runner: CliRunner) -> None:
    result = runner.invoke(app, ["record"])
    assert result.exit_code != 0
    assert "cassette" in result.stdout.lower() or "cassette" in (result.stderr or "").lower()


def test_record_passes_config_to_serve(
    runner: CliRunner, mock_serve: MagicMock, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"
    result = runner.invoke(
        app,
        [
            "record",
            "--cassette",
            str(cassette),
            "--port",
            "9999",
            "--upstream",
            "https://api.example.com",
        ],
    )
    assert result.exit_code == 0, result.stdout

    cfg = _last_config(mock_serve)
    assert cfg.mode == "record"
    assert cfg.cassette_path == str(cassette)
    assert cfg.port == 9999
    assert cfg.openai_upstream == "https://api.example.com"


# ─── replay ────────────────────────────────────────────────────────────


def test_replay_requires_existing_cassette(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "absent.jsonl"
    result = runner.invoke(app, ["replay", "--cassette", str(missing)])
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_replay_passes_config_to_serve(
    runner: CliRunner, mock_serve: MagicMock, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"
    cassette.write_text("")  # exists but empty

    result = runner.invoke(app, ["replay", "--cassette", str(cassette)])
    assert result.exit_code == 0, result.stdout

    cfg = _last_config(mock_serve)
    assert cfg.mode == "replay"
    assert cfg.cassette_path == str(cassette)


# ─── auto ──────────────────────────────────────────────────────────────


def test_auto_passes_config_to_serve(
    runner: CliRunner, mock_serve: MagicMock, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"  # doesn't need to exist for auto
    result = runner.invoke(app, ["auto", "--cassette", str(cassette)])
    assert result.exit_code == 0, result.stdout

    cfg = _last_config(mock_serve)
    assert cfg.mode == "auto"


def test_auto_uses_default_host_and_port(
    runner: CliRunner, mock_serve: MagicMock, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"
    result = runner.invoke(app, ["auto", "--cassette", str(cassette)])
    assert result.exit_code == 0

    cfg = _last_config(mock_serve)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 7878
