"""Sprint 5.4 — diff primitives."""

from __future__ import annotations

from reel.analytics.diff import align_entries, compare_entries
from reel.cassette.schema import (
    CassetteEntry,
    CassetteRequest,
    CassetteResponse,
)
from reel.cassette.writer import generate_id, now_iso


def _entry(
    *,
    fingerprint: str = "sha256:a",
    provider: str = "openai",
    model: str | None = "gpt-5",
    status: int = 200,
    response_body: dict[str, object] | None = None,
) -> CassetteEntry:
    request_body: dict[str, object] = {"messages": []}
    if model is not None:
        request_body = {"model": model, **request_body}
    return CassetteEntry(
        id=generate_id(),
        ts=now_iso(),
        provider=provider,
        request=CassetteRequest(
            method="POST",
            path="/v1/chat/completions",
            fingerprint=fingerprint,
            body=request_body,
        ),
        response=CassetteResponse(
            status=status,
            headers={},
            body=response_body if response_body is not None else {"text": "hi"},
        ),
    )


# ─── align_entries ─────────────────────────────────────────────────────


def test_align_pairs_by_fingerprint() -> None:
    left = [_entry(fingerprint="fp-1"), _entry(fingerprint="fp-2")]
    right = [_entry(fingerprint="fp-2"), _entry(fingerprint="fp-1")]
    aligned = align_entries(left, right)

    assert len(aligned) == 2
    # left[0] (fp-1) paired with right[1] (fp-1)
    assert aligned[0].left is left[0]
    assert aligned[0].right is right[1]
    assert aligned[0].kind == "both"
    # left[1] (fp-2) paired with right[0] (fp-2)
    assert aligned[1].left is left[1]
    assert aligned[1].right is right[0]
    assert aligned[1].kind == "both"


def test_align_marks_left_only_entries() -> None:
    left = [_entry(fingerprint="fp-1"), _entry(fingerprint="fp-missing")]
    right = [_entry(fingerprint="fp-1")]
    aligned = align_entries(left, right)

    assert [a.kind for a in aligned] == ["both", "left_only"]
    assert aligned[1].left is left[1]
    assert aligned[1].right is None


def test_align_marks_right_only_entries() -> None:
    left = [_entry(fingerprint="fp-1")]
    right = [_entry(fingerprint="fp-1"), _entry(fingerprint="fp-new")]
    aligned = align_entries(left, right)

    assert [a.kind for a in aligned] == ["both", "right_only"]
    assert aligned[1].left is None
    assert aligned[1].right is right[1]


def test_align_changed_when_response_differs() -> None:
    left = [_entry(fingerprint="fp-1", response_body={"text": "old"})]
    right = [_entry(fingerprint="fp-1", response_body={"text": "new"})]
    aligned = align_entries(left, right)

    assert len(aligned) == 1
    assert aligned[0].kind == "changed"


def test_align_handles_duplicate_fingerprints_fifo() -> None:
    left = [
        _entry(fingerprint="fp-dup", response_body={"i": 1}),
        _entry(fingerprint="fp-dup", response_body={"i": 2}),
    ]
    right = [
        _entry(fingerprint="fp-dup", response_body={"i": 1}),
        _entry(fingerprint="fp-dup", response_body={"i": 2}),
    ]
    aligned = align_entries(left, right)

    assert len(aligned) == 2
    # FIFO pairing: left[0]↔right[0], left[1]↔right[1]
    assert aligned[0].left is left[0] and aligned[0].right is right[0]
    assert aligned[1].left is left[1] and aligned[1].right is right[1]
    assert aligned[0].kind == "both"
    assert aligned[1].kind == "both"


def test_align_empty_inputs() -> None:
    assert align_entries([], []) == []


def test_align_right_only_preserves_order() -> None:
    left: list[CassetteEntry] = []
    right = [_entry(fingerprint="a"), _entry(fingerprint="b"), _entry(fingerprint="c")]
    aligned = align_entries(left, right)
    assert [a.right for a in aligned] == right


# ─── compare_entries ───────────────────────────────────────────────────


def test_compare_flags_model_change() -> None:
    left = _entry(model="gpt-5")
    right = _entry(model="gpt-4o")
    diff = compare_entries(left, right)

    assert diff.model_changed is True
    assert diff.status_changed is False
    assert any("model" in line for line in diff.lines)


def test_compare_flags_status_change() -> None:
    left = _entry(status=200)
    right = _entry(status=429)
    diff = compare_entries(left, right)

    assert diff.status_changed is True
    assert any("status" in line for line in diff.lines)


def test_compare_flags_body_change() -> None:
    left = _entry(response_body={"text": "old"})
    right = _entry(response_body={"text": "new"})
    diff = compare_entries(left, right)

    assert diff.body_changed is True
    assert any("body" in line for line in diff.lines)


def test_compare_identical_entries_have_no_changes() -> None:
    left = _entry()
    right = _entry()
    # Need request bodies and response bodies to match exactly.
    diff = compare_entries(left, right)
    assert diff.status_changed is False
    assert diff.model_changed is False
    assert diff.body_changed is False


def test_tokens_delta_computed_when_both_sides_have_usage() -> None:
    left = _entry(
        response_body={"text": "a", "usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    )
    right = _entry(
        response_body={"text": "a", "usage": {"prompt_tokens": 12, "completion_tokens": 35}}
    )
    diff = compare_entries(left, right)
    assert diff.tokens_delta == 15


def test_tokens_delta_supports_anthropic_shape() -> None:
    left = _entry(response_body={"usage": {"input_tokens": 10, "output_tokens": 5}})
    right = _entry(response_body={"usage": {"input_tokens": 10, "output_tokens": 9}})
    diff = compare_entries(left, right)
    assert diff.tokens_delta == 4


def test_tokens_delta_none_when_one_side_missing_usage() -> None:
    left = _entry(response_body={"text": "no usage"})
    right = _entry(response_body={"usage": {"completion_tokens": 42}})
    diff = compare_entries(left, right)
    assert diff.tokens_delta is None


def test_tokens_delta_none_when_both_missing_usage() -> None:
    left = _entry(response_body={"text": "x"})
    right = _entry(response_body={"text": "y"})
    diff = compare_entries(left, right)
    assert diff.tokens_delta is None
