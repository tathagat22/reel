"""Sprint 1.5 — reader, matcher, and Cassette facade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reel.cassette.matcher import find_exact
from reel.cassette.reader import CassetteReader
from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.store import Cassette
from reel.cassette.writer import generate_id, now_iso


def _entry(fp: str = "sha256:abc", body: object | None = None) -> CassetteEntry:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(
            method="POST",
            path="/v1/chat/completions",
            fingerprint=fp,
            body={"model": "gpt-5"},
        ),
        response=CassetteResponse(
            status=200,
            headers={"content-type": "application/json"},
            body=body if body is not None else {"choices": [{"message": {"content": "hi"}}]},
        ),
    )


# ─── Reader ────────────────────────────────────────────────────────────


def test_reader_returns_empty_for_missing_file(tmp_path: Path) -> None:
    reader = CassetteReader(tmp_path / "missing.jsonl")
    assert not reader.exists()
    assert reader.load_all() == []
    assert list(reader.iter_entries()) == []


def test_reader_returns_empty_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.touch()
    reader = CassetteReader(path)
    assert reader.exists()
    assert reader.load_all() == []


def test_reader_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    e1 = _entry("sha256:1")
    e2 = _entry("sha256:2")
    path.write_text(e1.model_dump_json() + "\n\n\n" + e2.model_dump_json() + "\n")

    reader = CassetteReader(path)
    loaded = reader.load_all()
    assert len(loaded) == 2
    assert loaded[0].request.fingerprint == "sha256:1"
    assert loaded[1].request.fingerprint == "sha256:2"


def test_reader_raises_on_malformed_line(tmp_path: Path) -> None:
    """Silently dropping corrupt lines would mask drift. Loud > silent."""
    path = tmp_path / "tape.jsonl"
    path.write_text("not-valid-json\n")
    reader = CassetteReader(path)
    with pytest.raises(ValueError):
        reader.load_all()


# ─── Matcher ───────────────────────────────────────────────────────────


def test_matcher_returns_none_when_no_match() -> None:
    entries = [_entry("sha256:1"), _entry("sha256:2")]
    assert find_exact(entries, "sha256:missing") is None


def test_matcher_returns_single_match() -> None:
    entries = [_entry("sha256:1"), _entry("sha256:2")]
    found = find_exact(entries, "sha256:2")
    assert found is not None
    assert found.request.fingerprint == "sha256:2"


def test_matcher_returns_most_recent_when_multiple() -> None:
    e1 = _entry("sha256:dup", body={"choices": [{"text": "first"}]})
    e2 = _entry("sha256:dup", body={"choices": [{"text": "second"}]})
    found = find_exact([e1, e2], "sha256:dup")
    assert found is not None
    assert found.response.body == {"choices": [{"text": "second"}]}


def test_matcher_returns_none_for_empty_entries() -> None:
    assert find_exact([], "sha256:any") is None


# ─── Cassette facade ───────────────────────────────────────────────────


async def test_cassette_starts_empty_when_path_missing(tmp_path: Path) -> None:
    cassette = Cassette(tmp_path / "new.jsonl")
    assert len(cassette) == 0
    assert cassette.find("sha256:x") is None


async def test_cassette_loads_existing_entries(tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    e1 = _entry("sha256:1")
    e2 = _entry("sha256:2")
    path.write_text(e1.model_dump_json() + "\n" + e2.model_dump_json() + "\n")

    cassette = Cassette(path)
    assert len(cassette) == 2
    assert cassette.find("sha256:2") is not None


async def test_cassette_append_updates_in_memory_and_disk(tmp_path: Path) -> None:
    path = tmp_path / "tape.jsonl"
    cassette = Cassette(path)
    await cassette.append(_entry("sha256:abc"))

    assert len(cassette) == 1
    assert cassette.find("sha256:abc") is not None

    # Disk has it too.
    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["request"]["fingerprint"] == "sha256:abc"


async def test_cassette_append_then_find_returns_just_written(tmp_path: Path) -> None:
    cassette = Cassette(tmp_path / "tape.jsonl")
    new = _entry("sha256:new")
    await cassette.append(new)
    found = cassette.find("sha256:new")
    assert found is not None
    assert found.id == new.id


async def test_cassette_reload_sees_disk_changes(tmp_path: Path) -> None:
    """A freshly-instantiated Cassette reads from disk."""
    path = tmp_path / "tape.jsonl"

    c1 = Cassette(path)
    await c1.append(_entry("sha256:a"))
    await c1.append(_entry("sha256:b"))

    c2 = Cassette(path)
    assert len(c2) == 2
    assert c2.find("sha256:a") is not None
    assert c2.find("sha256:b") is not None
