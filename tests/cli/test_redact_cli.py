"""Sprint 3.8 — reel redact CLI."""

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


def _entry_line(body: object) -> str:
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    entry = CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(method="POST", path=CHAT, fingerprint=fp, body=body),
        response=CassetteResponse(
            status=200,
            headers={"x-debug": "Bearer eyJabc.payload.sig"},
            body={"text": "secret sk-FAKE_FIXTURE_TEST_NOT_REAL leak", "contact": "x@example.com"},
        ),
    )
    return entry.model_dump_json()


def _write(path: Path, lines: list[str], *, meta: dict[str, object] | None = None) -> None:
    out: list[str] = []
    if meta is not None:
        out.append(json.dumps({"_meta": meta}))
    out.extend(lines)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def test_redact_missing_cassette_exits_2(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    result = runner.invoke(app, ["redact", "--cassette", str(missing)])
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_redact_scrubs_in_place(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line({"model": "gpt-5", "messages": []})])

    result = runner.invoke(app, ["redact", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout

    raw = path.read_text()
    assert "sk-FAKE_FIXTURE_TEST_NOT_REAL" not in raw
    assert "x@example.com" not in raw
    assert "[redacted:openai-key]" in raw
    assert "[redacted:email]" in raw


def test_redact_keeps_pii_with_keep_pii_flag(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line({"model": "gpt-5", "messages": []})])

    result = runner.invoke(app, ["redact", "--cassette", str(path), "--keep-pii"])
    assert result.exit_code == 0, result.stdout

    raw = path.read_text()
    # Secrets always scrubbed even with --keep-pii
    assert "sk-FAKE_FIXTURE_TEST_NOT_REAL" not in raw
    # PII preserved
    assert "x@example.com" in raw


def test_redact_dry_run_does_not_modify(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line({"model": "gpt-5", "messages": []})])
    original = path.read_text()

    result = runner.invoke(app, ["redact", "--cassette", str(path), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert path.read_text() == original
    assert "dry-run" in result.stdout


def test_redact_writes_to_output_path(runner: CliRunner, tmp_path: Path) -> None:
    src = tmp_path / "tape.jsonl"
    dst = tmp_path / "clean.jsonl"
    _write(src, [_entry_line({"model": "gpt-5", "messages": []})])
    original = src.read_text()

    result = runner.invoke(app, ["redact", "--cassette", str(src), "--output", str(dst)])
    assert result.exit_code == 0, result.stdout

    # Original untouched, dest scrubbed.
    assert src.read_text() == original
    assert dst.exists()
    assert "sk-FAKE_FIXTURE_TEST_NOT_REAL" not in dst.read_text()


def test_redact_preserves_meta_line(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [_entry_line({"model": "gpt-5", "messages": []})],
        meta={"match": {"mode": "ignore-fields", "ignore_fields": ["request_id"]}},
    )

    result = runner.invoke(app, ["redact", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout

    first_line = path.read_text().splitlines()[0]
    parsed = json.loads(first_line)
    assert "_meta" in parsed
    assert parsed["_meta"]["match"]["mode"] == "ignore-fields"


def test_redact_reports_counts(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line({"model": "gpt-5", "messages": []})])

    result = runner.invoke(app, ["redact", "--cassette", str(path)])
    assert result.exit_code == 0
    out = result.stdout
    assert "entries:" in out
    assert "secrets" in out
    assert "PII" in out
