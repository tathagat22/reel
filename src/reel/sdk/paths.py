"""Cassette path inference.

Convention: cassettes for ``tests/foo/test_bar.py::test_baz`` live at
``tests/foo/cassettes/test_bar/test_baz.jsonl``. Parametrized tests with
square-bracket suffixes have the brackets sanitized into double underscores
so the resulting filenames stay portable across OSes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def default_cassette_path(node: Any) -> Path:
    """Compute the default cassette path for a pytest test node."""
    test_file = Path(str(node.fspath))
    name = _safe_name(str(node.name))
    return test_file.parent / "cassettes" / test_file.stem / f"{name}.jsonl"


def _safe_name(name: str) -> str:
    """Sanitize a pytest node name for use as a filename."""
    return (
        name.replace("[", "__")
        .replace("]", "")
        .replace("/", "_")
        .replace(" ", "_")
        .replace(":", "_")
    )
