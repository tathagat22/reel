"""Sprint 3.9 — pre-commit hook script behaves end-to-end."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "pre-commit-cassette-check.py"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Initialize a throwaway git repo, return its path."""
    if shutil.which("git") is None:
        pytest.skip("git not available")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.local")
    _git(tmp_path, "config", "user.name", "test")
    return tmp_path


def _run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_passes_when_no_jsonl_staged(repo: Path) -> None:
    (repo / "foo.txt").write_text("not jsonl")
    _git(repo, "add", "foo.txt")
    r = _run_hook(repo)
    assert r.returncode == 0


def test_passes_when_jsonl_has_no_secrets(repo: Path) -> None:
    (repo / "clean.jsonl").write_text(
        '{"id":"x","ts":"2026-01-01T00:00:00+00:00","provider":"openai",'
        '"request":{"method":"POST","path":"/v1/chat/completions",'
        '"fingerprint":"sha256:abc","body":{"model":"gpt-5","messages":[]}},'
        '"response":{"status":200,"headers":{},"body":{"ok":true}}}\n'
    )
    _git(repo, "add", "clean.jsonl")
    r = _run_hook(repo)
    assert r.returncode == 0, r.stderr


def test_refuses_jsonl_with_openai_key(repo: Path) -> None:
    (repo / "tainted.jsonl").write_text('{"x":"leaked sk-FAKE_FIXTURE_TEST_NOT_REAL in body"}\n')
    _git(repo, "add", "tainted.jsonl")
    r = _run_hook(repo)
    assert r.returncode == 1
    assert "secret" in r.stderr.lower()
    assert "tainted.jsonl" in r.stderr


def test_refuses_jsonl_with_bearer_token(repo: Path) -> None:
    (repo / "auth.jsonl").write_text('{"h":"Bearer eyJ.payload.sig"}\n')
    _git(repo, "add", "auth.jsonl")
    r = _run_hook(repo)
    assert r.returncode == 1


def test_only_inspects_staged_content_not_working_tree(repo: Path) -> None:
    """The hook reads `git show :file`, so unstaged edits don't leak through."""
    path = repo / "tape.jsonl"
    path.write_text('{"clean":true}\n')
    _git(repo, "add", "tape.jsonl")

    # Now write a secret to the working tree (NOT staged).
    path.write_text('{"x":"sk-FAKE_FIXTURE_TEST_NOT_REAL"}\n')

    r = _run_hook(repo)
    # Hook sees the staged content (clean) → passes.
    assert r.returncode == 0, r.stderr
