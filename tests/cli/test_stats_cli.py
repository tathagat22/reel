"""Sprint 5.5 — reel stats CLI integration.

The ``stats`` command is wired into the top-level Typer ``app`` separately;
this test exercises ``stats.run`` directly through its own throwaway Typer
app so it remains self-contained even before the wire-up lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from reel.cassette.schema import (
    CassetteEntry,
    CassetteRequest,
    CassetteResponse,
    StreamChunk,
)
from reel.cassette.writer import generate_id, now_iso
from reel.cli.commands import stats as stats_cmd


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    # Typer collapses to a single-command CLI when only one command is
    # registered (dropping the command name from the parser). Pin
    # multi-command semantics with an explicit callback so `reel stats ...`
    # parses the way the production CLI will.
    a = typer.Typer()

    @a.callback()
    def _root() -> None:  # pyright: ignore[reportUnusedFunction]
        """Test harness root."""

    a.command(name="stats")(stats_cmd.run)
    return a


def _entry_line(
    *,
    provider: str = "openai",
    status: int = 200,
    usage: dict[str, int] | None = None,
    stream_chunks: list[StreamChunk] | None = None,
) -> str:
    body: dict[str, object] | None = None
    if stream_chunks is None:
        body = {"id": "resp-1"}
        if usage is not None:
            body["usage"] = usage
    entry = CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(
            method="POST",
            path="/v1/chat/completions",
            fingerprint="sha256:x",
            body={"model": "gpt-5", "messages": []},
        ),
        response=CassetteResponse(
            status=status,
            headers={},
            body=body,
            stream_chunks=stream_chunks,
        ),
    )
    return entry.model_dump_json()


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_stats_missing_cassette_exits_2(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["stats", "--cassette", str(tmp_path / "nope.jsonl")])
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_stats_summary_prints_entries_line(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            _entry_line(usage={"prompt_tokens": 10, "completion_tokens": 5}),
            _entry_line(provider="anthropic", status=429),
        ],
    )

    result = runner.invoke(app, ["stats", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    # Required smoke assertion: prints an "entries" line.
    assert "entries" in result.stdout
    # Showed multi-provider breakdown.
    assert "openai" in result.stdout
    assert "anthropic" in result.stdout
    # Error rate rendered.
    assert "%" in result.stdout
    # Token totals rendered.
    assert "Tokens" in result.stdout


def test_stats_summary_with_streaming_shows_ttft(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            json.dumps(
                json.loads(
                    _entry_line(
                        stream_chunks=[
                            StreamChunk(data={"delta": "a"}, t_offset_ms=120),
                            StreamChunk(data={"delta": "b"}, t_offset_ms=300),
                        ]
                    )
                )
            ),
        ],
    )

    result = runner.invoke(app, ["stats", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    assert "TTFT" in result.stdout


def test_stats_no_streaming_entries_skips_ttft(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line()])

    result = runner.invoke(app, ["stats", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    assert "no streaming entries" in result.stdout


def test_stats_by_provider(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            _entry_line(provider="openai"),
            _entry_line(provider="openai"),
            _entry_line(provider="anthropic"),
        ],
    )

    result = runner.invoke(app, ["stats", "--cassette", str(path), "--by", "provider"])
    assert result.exit_code == 0, result.stdout
    assert "openai" in result.stdout
    assert "anthropic" in result.stdout


def test_stats_by_status(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(status=200), _entry_line(status=500)])

    result = runner.invoke(app, ["stats", "--cassette", str(path), "--by", "status"])
    assert result.exit_code == 0, result.stdout
    assert "2xx" in result.stdout
    assert "5xx" in result.stdout


def test_stats_invalid_by_exits_2(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line()])

    result = runner.invoke(app, ["stats", "--cassette", str(path), "--by", "garbage"])
    assert result.exit_code == 2
    assert "provider" in result.stdout or "summary" in result.stdout
