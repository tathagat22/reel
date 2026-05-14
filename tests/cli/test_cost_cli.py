"""Sprint 5.3 — reel cost CLI integration.

The ``run`` function is tested through a standalone Typer app rather than
``reel.cli.main:app`` so this suite is independent of how the cost command
gets wired into the main CLI.
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
from reel.cli.commands.cost import run as cost_run

CHAT = "/v1/chat/completions"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    """Standalone Typer app exposing only the ``cost`` command.

    Two registrations: the second one disambiguates Typer's "single command"
    optimization so ``cost`` actually becomes a subcommand on the CLI.
    """
    a = typer.Typer()
    a.command(name="cost")(cost_run)
    a.command(name="_noop")(_noop)
    return a


def _noop() -> None:  # pragma: no cover - present only to force subcommand mode
    """Placeholder so Typer treats the app as multi-command."""


def _entry_line(
    *,
    provider: str = "openai",
    model: str = "gpt-5",
    prompt_tokens: int | None = 1000,
    completion_tokens: int | None = 500,
    usage_shape: str = "openai",
) -> str:
    body: dict[str, object] = {"model": model, "messages": []}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)

    response_body: dict[str, object] | None
    if prompt_tokens is None and completion_tokens is None:
        response_body = {"id": "resp_no_usage"}
    elif usage_shape == "openai":
        response_body = {
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        }
    elif usage_shape == "anthropic":
        response_body = {
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
            }
        }
    elif usage_shape == "gemini":
        response_body = {
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": completion_tokens,
            }
        }
    else:
        raise AssertionError(f"unknown usage_shape: {usage_shape}")

    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(method="POST", path=CHAT, fingerprint=fp, body=body),
        response=CassetteResponse(status=200, headers={}, body=response_body),
    ).model_dump_json()


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── error paths ───────────────────────────────────────────────────────


def test_cost_missing_cassette_exits_2(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    result = runner.invoke(app, ["cost", "--cassette", str(tmp_path / "nope.jsonl")])
    assert result.exit_code == 2
    assert "not found" in result.stdout


def test_cost_invalid_by_exits_2(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line()])
    result = runner.invoke(app, ["cost", "--cassette", str(path), "--by", "bogus"])
    assert result.exit_code == 2
    assert "provider" in result.stdout


# ─── rendering ─────────────────────────────────────────────────────────


def test_cost_renders_table_with_total_row(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(model="gpt-5", prompt_tokens=2_000_000, completion_tokens=0)])

    result = runner.invoke(app, ["cost", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    # Header / structure
    assert "input tokens" in result.stdout
    assert "output tokens" in result.stdout
    assert "TOTAL" in result.stdout
    # 2M tokens of gpt-5 input → $10.00
    assert "$10.00" in result.stdout
    assert "openai/gpt-5" in result.stdout


def test_cost_by_provider_groups_correctly(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            _entry_line(model="gpt-5", prompt_tokens=1000, completion_tokens=1000),
            _entry_line(model="gpt-4o", prompt_tokens=1000, completion_tokens=1000),
            _entry_line(
                provider="anthropic",
                model="claude-haiku-4-5",
                prompt_tokens=1000,
                completion_tokens=1000,
                usage_shape="anthropic",
            ),
        ],
    )

    result = runner.invoke(app, ["cost", "--cassette", str(path), "--by", "provider"])
    assert result.exit_code == 0, result.stdout
    assert "openai" in result.stdout
    assert "anthropic" in result.stdout
    # No per-model rows should leak in when grouping by provider
    assert "gpt-5" not in result.stdout
    assert "claude-haiku-4-5" not in result.stdout


def test_cost_by_total_shows_single_row(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            _entry_line(prompt_tokens=1_000_000, completion_tokens=0),
            _entry_line(prompt_tokens=1_000_000, completion_tokens=0),
        ],
    )
    result = runner.invoke(app, ["cost", "--cassette", str(path), "--by", "total"])
    assert result.exit_code == 0, result.stdout
    assert "TOTAL" in result.stdout
    # 2M tokens x $5/1M = $10.00
    assert "$10.00" in result.stdout


def test_cost_custom_pricing_overrides_defaults(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    cassette = tmp_path / "tape.jsonl"
    _write(cassette, [_entry_line(model="gpt-5", prompt_tokens=1_000_000, completion_tokens=0)])

    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps({"openai": {"gpt-5": {"input": 100.0, "output": 0.0}}}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["cost", "--cassette", str(cassette), "--pricing", str(pricing)],
    )
    assert result.exit_code == 0, result.stdout
    # 1M tokens x $100 = $100.00 (custom price)
    assert "$100.00" in result.stdout


def test_cost_unknown_model_marked_na(runner: CliRunner, app: typer.Typer, tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    _write(path, [_entry_line(model="mystery-future-llm", prompt_tokens=100, completion_tokens=50)])

    result = runner.invoke(app, ["cost", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    assert "N/A" in result.stdout
    assert "mystery-future-llm" in result.stdout


def test_cost_anthropic_and_gemini_shapes_aggregate(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            _entry_line(
                provider="anthropic",
                model="claude-sonnet-4-6",
                prompt_tokens=1_000_000,
                completion_tokens=0,
                usage_shape="anthropic",
            ),
            _entry_line(
                provider="gemini",
                model="gemini-1.5-flash",
                prompt_tokens=1_000_000,
                completion_tokens=0,
                usage_shape="gemini",
            ),
        ],
    )
    result = runner.invoke(app, ["cost", "--cassette", str(path), "--by", "model"])
    assert result.exit_code == 0, result.stdout
    # Rich may truncate long scope strings — match the unambiguous prefixes.
    assert "anthropic/" in result.stdout
    assert "gemini/" in result.stdout
    # claude-sonnet-4-6 input $3/1M, gemini-1.5-flash input $0.075/1M
    assert "$3.00" in result.stdout
    assert "$0.0750" in result.stdout


def test_cost_skips_entries_without_usage(
    runner: CliRunner, app: typer.Typer, tmp_path: Path
) -> None:
    path = tmp_path / "tape.jsonl"
    _write(
        path,
        [
            _entry_line(prompt_tokens=None, completion_tokens=None),
            _entry_line(prompt_tokens=1_000_000, completion_tokens=0),
        ],
    )
    result = runner.invoke(app, ["cost", "--cassette", str(path)])
    assert result.exit_code == 0, result.stdout
    # Only the priced entry should show up — total = $5.00
    assert "$5.00" in result.stdout
