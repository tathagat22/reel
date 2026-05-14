"""Sprint 3.5 — cassette-level _meta line + match config wiring."""

from __future__ import annotations

import json
from pathlib import Path

from reel.adapters.openai import adapter as openai_adapter
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.store import Cassette
from reel.cassette.writer import generate_id, now_iso

CHAT = "/v1/chat/completions"


def _entry_line(body: object, fp: str) -> str:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(method="POST", path=CHAT, fingerprint=fp, body=body),
        response=CassetteResponse(status=200, headers={}, body={"ok": True}),
    ).model_dump_json()


def _write_cassette(path: Path, *, meta: dict[str, object] | None, entries: list[str]) -> None:
    lines: list[str] = []
    if meta is not None:
        lines.append(json.dumps({"_meta": meta}))
    lines.extend(entries)
    path.write_text("\n".join(lines) + "\n")


def test_no_meta_line_yields_default_config(tmp_path: Path) -> None:
    body = {"model": "gpt-5", "messages": []}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    _write_cassette(tmp_path / "tape.jsonl", meta=None, entries=[_entry_line(body, fp)])

    cassette = Cassette(tmp_path / "tape.jsonl")
    assert cassette.match_config.mode == "normalized"
    assert cassette.match_config.ignore_fields == ()


def test_meta_line_loads_ignore_fields_config(tmp_path: Path) -> None:
    body = {"model": "gpt-5", "messages": [], "request_id": "abc-123"}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    _write_cassette(
        tmp_path / "tape.jsonl",
        meta={"match": {"mode": "ignore-fields", "ignore_fields": ["request_id"]}},
        entries=[_entry_line(body, fp)],
    )

    cassette = Cassette(tmp_path / "tape.jsonl")
    assert cassette.match_config.mode == "ignore-fields"
    assert cassette.match_config.ignore_fields == ("request_id",)


def test_meta_line_not_returned_as_entry(tmp_path: Path) -> None:
    body = {"model": "gpt-5", "messages": []}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    _write_cassette(
        tmp_path / "tape.jsonl",
        meta={"match": {"mode": "exact"}},
        entries=[_entry_line(body, fp)],
    )

    cassette = Cassette(tmp_path / "tape.jsonl")
    assert len(cassette) == 1  # meta line skipped
    assert cassette.entries()[0].request.fingerprint == fp


def test_find_smart_uses_configured_ignore_fields(tmp_path: Path) -> None:
    """An entry with request_id=abc matches an incoming request with request_id=xyz."""
    stored = {"model": "gpt-5", "messages": [], "request_id": "abc-123"}
    stored_fp = openai_adapter.fingerprint(json.dumps(stored).encode(), endpoint=CHAT)
    _write_cassette(
        tmp_path / "tape.jsonl",
        meta={"match": {"mode": "ignore-fields", "ignore_fields": ["request_id"]}},
        entries=[_entry_line(stored, stored_fp)],
    )

    cassette = Cassette(tmp_path / "tape.jsonl")
    incoming = b'{"model":"gpt-5","messages":[],"request_id":"xyz-999"}'
    result = cassette.find_smart(body=incoming, path=CHAT, adapter=openai_adapter)
    assert result is not None


def test_find_smart_defaults_to_normalized_when_no_meta(tmp_path: Path) -> None:
    body = {"model": "gpt-5", "messages": []}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    _write_cassette(tmp_path / "tape.jsonl", meta=None, entries=[_entry_line(body, fp)])

    cassette = Cassette(tmp_path / "tape.jsonl")
    found = cassette.find_smart(body=json.dumps(body).encode(), path=CHAT, adapter=openai_adapter)
    assert found is not None


def test_meta_in_middle_of_file_is_ignored(tmp_path: Path) -> None:
    """Only the first non-blank line is inspected for meta — anything later is data."""
    body = {"model": "gpt-5", "messages": []}
    fp = openai_adapter.fingerprint(json.dumps(body).encode(), endpoint=CHAT)
    cassette_path = tmp_path / "tape.jsonl"
    # Entry first, then a `_meta` line — should be ignored at the entry level
    # (the reader skips _meta lines anywhere), but match_config stays at default.
    cassette_path.write_text(
        _entry_line(body, fp) + "\n" + json.dumps({"_meta": {"match": {"mode": "exact"}}}) + "\n"
    )

    cassette = Cassette(cassette_path)
    assert cassette.match_config.mode == "normalized"  # default — meta wasn't at the top
    assert len(cassette) == 1


def test_replay_404_response_includes_match_mode(tmp_path: Path) -> None:
    """The 404 diagnostic surfaces which mode was used."""
    from starlette.testclient import TestClient

    from reel.proxy.config import ProxyConfig
    from reel.proxy.server import create_app

    _write_cassette(
        tmp_path / "tape.jsonl",
        meta={"match": {"mode": "exact"}},
        entries=[],
    )

    cfg = ProxyConfig(mode="replay", cassette_path=str(tmp_path / "tape.jsonl"))
    with TestClient(create_app(cfg)) as client:
        r = client.post(CHAT, json={"model": "gpt-5", "messages": []})

    assert r.status_code == 404
    assert r.json()["match_mode"] == "exact"
