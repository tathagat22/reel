"""Sprint 1.4 — JSONL writer + schema round trip."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from reel.cassette.schema import CassetteEntry, CassetteRequest, CassetteResponse
from reel.cassette.writer import CassetteWriter, generate_id, now_iso


def _entry(fingerprint: str = "sha256:abc") -> CassetteEntry:
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider="openai",
        request=CassetteRequest(
            method="POST",
            path="/v1/chat/completions",
            fingerprint=fingerprint,
            body={"model": "gpt-5", "messages": []},
        ),
        response=CassetteResponse(
            status=200,
            headers={"content-type": "application/json"},
            body={"id": "chatcmpl-xyz"},
        ),
    )


async def test_append_writes_one_line(tmp_path: Path) -> None:
    writer = CassetteWriter(tmp_path / "tape.jsonl")
    await writer.append(_entry())

    contents = (tmp_path / "tape.jsonl").read_text()
    lines = contents.splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed["request"]["fingerprint"] == "sha256:abc"
    assert parsed["response"]["status"] == 200
    assert parsed["schema_version"] == 1


async def test_append_preserves_order(tmp_path: Path) -> None:
    writer = CassetteWriter(tmp_path / "tape.jsonl")
    for i in range(5):
        await writer.append(_entry(fingerprint=f"sha256:{i}"))

    lines = (tmp_path / "tape.jsonl").read_text().splitlines()
    assert len(lines) == 5
    fingerprints = [json.loads(line)["request"]["fingerprint"] for line in lines]
    assert fingerprints == [f"sha256:{i}" for i in range(5)]


async def test_append_creates_parent_directories(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "path" / "tape.jsonl"
    writer = CassetteWriter(nested)
    await writer.append(_entry())
    assert nested.exists()


async def test_concurrent_appends_do_not_corrupt(tmp_path: Path) -> None:
    writer = CassetteWriter(tmp_path / "tape.jsonl")

    async def append_one(i: int) -> None:
        await writer.append(_entry(fingerprint=f"sha256:{i:04d}"))

    await asyncio.gather(*(append_one(i) for i in range(50)))

    lines = (tmp_path / "tape.jsonl").read_text().splitlines()
    assert len(lines) == 50
    # Every line is valid JSON (no corruption from concurrent writes).
    fingerprints = {json.loads(line)["request"]["fingerprint"] for line in lines}
    assert len(fingerprints) == 50


def test_generate_id_is_unique() -> None:
    ids = {generate_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_generate_id_has_expected_shape() -> None:
    rid = generate_id()
    assert rid.startswith("req_")
    parts = rid.split("_")
    assert len(parts) == 3
    assert parts[1].isdigit() and len(parts[1]) == 13  # ms timestamp
    assert len(parts[2]) == 8  # 4 bytes hex


def test_now_iso_is_utc() -> None:
    ts = now_iso()
    # ISO 8601 with timezone offset.
    assert "T" in ts
    assert ts.endswith("+00:00")


def test_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        CassetteEntry.model_validate(
            {
                "id": "req_x",
                "ts": now_iso(),
                "provider": "openai",
                "request": {
                    "method": "POST",
                    "path": "/v1/chat/completions",
                    "fingerprint": "sha256:x",
                },
                "response": {"status": 200},
                "extra_field": "not allowed",
            }
        )


async def test_round_trip_via_json(tmp_path: Path) -> None:
    """An entry written and read back is structurally identical."""
    writer = CassetteWriter(tmp_path / "tape.jsonl")
    original = _entry()
    await writer.append(original)

    raw = (tmp_path / "tape.jsonl").read_text().strip()
    parsed = CassetteEntry.model_validate_json(raw)

    assert parsed.id == original.id
    assert parsed.request.fingerprint == original.request.fingerprint
    assert parsed.request.body == original.request.body
    assert parsed.response.status == original.response.status
    assert parsed.response.body == original.response.body
