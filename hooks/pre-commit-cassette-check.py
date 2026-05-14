#!/usr/bin/env python3
"""Pre-commit hook — refuse staged cassettes that contain secret patterns.

Drop this into ``.git/hooks/pre-commit`` (chmod +x) or wire it via pre-commit
(``.pre-commit-config.yaml`` entry shown below) to make leaked-key commits
impossible.

The hook reads the **staged** content of every ``*.jsonl`` file (not the
working tree), so it catches commits even when the working file has already
been cleaned.

Exit codes:
    0  no secrets found in any staged cassette
    1  at least one secret pattern detected — commit aborted

pre-commit.yaml integration (optional):

.. code-block:: yaml

    repos:
      - repo: local
        hooks:
          - id: reel-cassette-secrets
            name: reel — refuse secret-tainted cassettes
            language: system
            entry: python hooks/pre-commit-cassette-check.py
            files: '\\.jsonl$'
            pass_filenames: false
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Patterns copied from reel.redact.secrets so the hook stays self-contained
# (no dependency on the installed package; runs in CI bare environments too).
SECRET_REGEXES = [
    r"sk-ant-api\d+-[A-Za-z0-9_\-]+",
    r"sk-proj-[A-Za-z0-9_\-]{20,}",
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"AIza[A-Za-z0-9_\-]{30,}",
    r"gh[ps]_[A-Za-z0-9]{30,}",
    r"github_pat_[A-Za-z0-9_]{50,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[baprs]-[A-Za-z0-9\-]+",
    r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=:+/]+",
]


def _staged_jsonl_files() -> list[Path]:
    """Return every ``*.jsonl`` that is staged for commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.endswith(".jsonl")]


def _staged_content(path: Path) -> str:
    """Return the staged (index) content of ``path``, not the working tree."""
    result = subprocess.run(
        ["git", "show", f":{path.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _scan(text: str) -> list[str]:
    """Return human-readable matches (capped) for the first detected secret patterns."""
    import re

    out: list[str] = []
    for raw in SECRET_REGEXES:
        m = re.search(raw, text)
        if m is not None:
            label = raw.split("[")[0].rstrip("\\")[:30]
            out.append(f"  pattern={label!r:<25} sample={m.group(0)[:40]}...")
    return out


def main() -> int:
    bad: list[tuple[Path, list[str]]] = []
    for jsonl in _staged_jsonl_files():
        content = _staged_content(jsonl)
        matches = _scan(content)
        if matches:
            bad.append((jsonl, matches))

    if not bad:
        return 0

    sys.stderr.write("\nreel: refusing commit — secret patterns detected in staged cassettes:\n\n")
    for path, matches in bad:
        sys.stderr.write(f"  {path}\n")
        for line in matches:
            sys.stderr.write(f"  {line}\n")
        sys.stderr.write("\n")
    sys.stderr.write(
        "  Run 'reel redact -c <file>' to scrub, then re-stage.\n"
        "  Or commit with --no-verify ONLY if you've reviewed and accept the contents.\n\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
