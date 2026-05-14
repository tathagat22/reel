"""Sprint 5.7 — reel doctor CLI integration."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from reel.cli.main import app
from reel.proxy.config import (
    DEFAULT_ANTHROPIC_UPSTREAM,
    DEFAULT_GEMINI_UPSTREAM,
    DEFAULT_OPENAI_UPSTREAM,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_doctor_happy_path_offline(runner: CliRunner) -> None:
    """`--skip-network` keeps the test offline and should always exit 0."""
    result = runner.invoke(app, ["doctor", "--skip-network"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    # All the section labels we promised in the spec show up.
    assert "python" in out.lower()
    assert "reel" in out.lower()
    assert "port" in out.lower()
    # Either label form is acceptable.
    assert "fuzzy" in out.lower() or "sentence-transformers" in out.lower()


def test_doctor_with_writable_cassette_parent(runner: CliRunner, tmp_path: Path) -> None:
    cassette = tmp_path / "tape.jsonl"  # parent (tmp_path) exists and is writable
    result = runner.invoke(app, ["doctor", "--skip-network", "--cassette", str(cassette)])
    assert result.exit_code == 0, result.stdout
    assert "cassette" in result.stdout.lower()


def test_doctor_with_nonexistent_cassette_parent_exits_1(runner: CliRunner) -> None:
    """If the parent dir doesn't exist, doctor must report a critical failure."""
    bad = Path("/this/does/not/exist/x.jsonl")
    result = runner.invoke(app, ["doctor", "--skip-network", "--cassette", str(bad)])
    assert result.exit_code == 1, result.stdout
    assert "does not exist" in result.stdout or "not writable" in result.stdout


def test_doctor_network_check_with_respx(runner: CliRunner) -> None:
    """Upstreams mocked to 200 — exit code stays 0, output mentions providers."""
    with respx.mock(assert_all_called=False) as mock:
        mock.head(DEFAULT_OPENAI_UPSTREAM).mock(return_value=httpx.Response(200))
        mock.head(DEFAULT_ANTHROPIC_UPSTREAM).mock(return_value=httpx.Response(200))
        mock.head(DEFAULT_GEMINI_UPSTREAM).mock(return_value=httpx.Response(200))
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "openai" in result.stdout
    assert "anthropic" in result.stdout
    assert "gemini" in result.stdout


def test_doctor_network_unreachable_is_not_critical(runner: CliRunner) -> None:
    """An upstream that fails DNS / TCP must not make doctor exit non-zero."""
    with respx.mock(assert_all_called=False) as mock:
        mock.head(DEFAULT_OPENAI_UPSTREAM).mock(side_effect=httpx.ConnectError("boom"))
        mock.head(DEFAULT_ANTHROPIC_UPSTREAM).mock(return_value=httpx.Response(200))
        mock.head(DEFAULT_GEMINI_UPSTREAM).mock(return_value=httpx.Response(200))
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "openai" in result.stdout
