"""Sprint 5.6 — structured per-request logging."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from reel.proxy.config import ProxyConfig
from reel.proxy.logs import emit
from reel.proxy.server import create_app

UPSTREAM = "https://api.openai.com"


# ─── Emitter unit tests ────────────────────────────────────────────────


def test_json_emit_writes_parseable_object(capsys: pytest.CaptureFixture[str]) -> None:
    emit({"a": 1, "b": "two", "n": None}, log_format="json")
    out = capsys.readouterr().out
    line = out.strip()
    parsed = json.loads(line)
    assert parsed == {"a": 1, "b": "two", "n": None}


def test_text_emit_renders_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    emit(
        {
            "ts": "2026-05-15T01:02:03.000+00:00",
            "mode": "auto",
            "provider": "openai",
            "method": "POST",
            "path": "/v1/chat/completions",
            "status": 200,
            "duration_ms": 42,
        },
        log_format="text",
    )
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "[auto] openai POST /v1/chat/completions -> 200 42ms" in out


def test_text_emit_falls_back_when_fields_missing(capsys: pytest.CaptureFixture[str]) -> None:
    emit({"mode": "record", "status": 404}, log_format="text")
    out = capsys.readouterr().out
    assert "[record]" in out
    assert "-> 404" in out


# ─── Integration via the proxy ─────────────────────────────────────────


def _proxy(mode: str, cassette: Path, *, log_format: str = "text") -> TestClient:
    return TestClient(
        create_app(
            ProxyConfig(
                mode=mode,  # type: ignore[arg-type]
                cassette_path=str(cassette),
                openai_upstream=UPSTREAM,
                log_format=log_format,  # type: ignore[arg-type]
            )
        )
    )


@respx.mock
def test_one_log_line_per_proxied_request_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    with _proxy("record", tmp_path / "tape.jsonl", log_format="json") as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]},
        )

    out_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    # Filter to JSON-parseable lines (uvicorn may add unrelated stderr/text).
    json_lines: list[dict[str, object]] = []
    for line in out_lines:
        try:
            json_lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    assert len(json_lines) == 1
    event = json_lines[0]
    assert event["mode"] == "record"
    assert event["provider"] == "openai"
    assert event["method"] == "POST"
    assert event["path"] == "/v1/chat/completions"
    assert event["status"] == 200
    assert isinstance(event["duration_ms"], int)
    assert event["duration_ms"] >= 0


def test_404_path_still_logged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with _proxy("record", tmp_path / "tape.jsonl", log_format="json") as client:
        r = client.get("/totally/unknown")
    assert r.status_code == 404

    out = capsys.readouterr().out
    events = [json.loads(line) for line in out.splitlines() if line.strip().startswith("{")]
    assert len(events) == 1
    assert events[0]["status"] == 404
    assert events[0]["provider"] is None  # no route resolved


@respx.mock
def test_text_format_one_line_per_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(f"{UPSTREAM}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    with _proxy("record", tmp_path / "tape.jsonl", log_format="text") as client:
        client.post("/v1/chat/completions", json={"model": "gpt-5", "messages": []})

    out = capsys.readouterr().out
    proxy_lines = [
        line
        for line in out.splitlines()
        if "[record] openai POST /v1/chat/completions -> 200" in line
    ]
    assert len(proxy_lines) == 1
