"""Sprint 5.2 — reel inspect CLI integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reel.adapters.openai import adapter as openai_adapter
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.writer import generate_id, now_iso
from reel.cli.main import app

CHAT = "/v1/chat/completions"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _entry_line(*, model: str = "gpt-5", status: int = 200, content: str = "hi") -> str:
    body = {"model": model, "messages": []}
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


def test_inspect_missing_cassette_exits_2(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", "--cassette", str(tmp_path / "nope.jsonl")])
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_inspect_prints_table_with_match_count(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(), _entry_line(model="gpt-4o", content="hello")])

    result = runner.invoke(app, ["inspect", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    assert "openai" in result.stdout
    assert "2 entries matched" in result.stdout


def test_inspect_status_filter(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(status=200), _entry_line(status=429)])

    result = runner.invoke(app, ["inspect", "--cassette", str(path), "--status", "4xx"])
    assert result.exit_code == 0, result.stdout
    assert "1 entry matched" in result.stdout
    assert "429" in result.stdout


def test_inspect_model_filter(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(model="gpt-5"), _entry_line(model="claude-opus-4-7")])

    result = runner.invoke(app, ["inspect", "--cassette", str(path), "--model", "opus"])
    assert result.exit_code == 0, result.stdout
    assert "1 entry matched" in result.stdout


def test_inspect_limit(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line() for _ in range(5)])

    result = runner.invoke(app, ["inspect", "--cassette", str(path), "--limit", "2"])
    assert result.exit_code == 0, result.stdout
    assert "2 entries matched" in result.stdout


def test_inspect_verbose(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(content="the verbose body content")])

    result = runner.invoke(app, ["inspect", "--cassette", str(path), "--verbose"])
    assert result.exit_code == 0, result.stdout
    assert "the verbose body content" in result.stdout


def test_inspect_regex(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [_entry_line(content="needle-here"), _entry_line(content="haystack-blob")],
    )

    result = runner.invoke(app, ["inspect", "--cassette", str(path), "--regex", "needle"])
    assert result.exit_code == 0, result.stdout
    assert "1 entry matched" in result.stdout
