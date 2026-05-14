"""Sprint 5.4 — reel diff CLI integration.

The ``run`` function is tested through a lightweight Typer app rather than
``reel.cli.main:app`` so this suite is independent of how/when the diff
command gets wired into the main CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from reel.adapters.openai import adapter as openai_adapter
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.writer import generate_id, now_iso
from reel.cli.commands.diff import run as diff_run

CHAT = "/v1/chat/completions"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    """Standalone Typer app exposing only the ``diff`` command.

    Two registrations: the second one disambiguates Typer's "single command"
    optimization so ``diff`` actually becomes a subcommand on the CLI.
    """
    a = typer.Typer()
    a.command(name="diff")(diff_run)
    a.command(name="_noop")(_noop)
    return a


def _noop() -> None:  # pragma: no cover - present only to force subcommand mode
    """Placeholder so Typer treats the app as multi-command."""


def _entry_line(*, model: str = "gpt-5", status: int = 200, content: str = "hi") -> str:
    body = {"model": model, "messages": [{"role": "user", "content": content}]}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(method="POST", path=CHAT, fingerprint=fp, body=body),
        response=CassetteResponse(status=status, headers={}, body={"text": content}),
    ).model_dump_json()


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── error paths ───────────────────────────────────────────────────────


def test_diff_missing_left_exits_2(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    right = tmp_path / "right.jsonl"
    _write(right, [_entry_line()])
    result = runner.invoke(
        app,
        ["diff", "--left", str(tmp_path / "missing.jsonl"), "--right", str(right)],
    )
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_diff_missing_right_exits_2(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    left = tmp_path / "left.jsonl"
    _write(left, [_entry_line()])
    result = runner.invoke(
        app,
        ["diff", "--left", str(left), "--right", str(tmp_path / "missing.jsonl")],
    )
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_diff_both_missing_exits_2(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "diff",
            "--left",
            str(tmp_path / "a.jsonl"),
            "--right",
            str(tmp_path / "b.jsonl"),
        ],
    )
    assert result.exit_code == 2


# ─── happy paths ───────────────────────────────────────────────────────


def test_diff_identical_cassettes_report_zero_changed(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    line = _entry_line(content="same")
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    _write(left, [line])
    _write(right, [line])

    result = runner.invoke(app, ["diff", "--left", str(left), "--right", str(right)])
    assert result.exit_code == 0, result.stdout
    assert "changed=0" in result.stdout
    assert "left-only=0" in result.stdout
    assert "right-only=0" in result.stdout
    assert "both=1" in result.stdout


def test_diff_reports_left_only_and_right_only(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    _write(left, [_entry_line(content="only-on-left")])
    _write(right, [_entry_line(content="only-on-right")])

    result = runner.invoke(app, ["diff", "--left", str(left), "--right", str(right)])
    assert result.exit_code == 0, result.stdout
    assert "left-only=1" in result.stdout
    assert "right-only=1" in result.stdout


def test_diff_short_flags_work(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    line = _entry_line()
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    _write(left, [line])
    _write(right, [line])

    result = runner.invoke(app, ["diff", "-l", str(left), "-r", str(right)])
    assert result.exit_code == 0, result.stdout
    assert "both=1" in result.stdout


def test_diff_no_show_bodies_flag(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    left_line = _entry_line(content="needle-on-left")
    right_line = _entry_line(content="haystack-on-right")
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    _write(left, [left_line])
    _write(right, [right_line])

    # Note: fingerprints will differ because content differs — so this is
    # left-only + right-only rather than 'changed'. Flag should still parse.
    result = runner.invoke(
        app,
        ["diff", "-l", str(left), "-r", str(right), "--no-show-bodies"],
    )
    assert result.exit_code == 0, result.stdout
