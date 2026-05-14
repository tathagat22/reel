"""Smoke test — Sprint 0 only. Real coverage starts in Sprint 1."""

from __future__ import annotations

import reel


def test_version_is_set() -> None:
    assert isinstance(reel.__version__, str)
    assert reel.__version__.count(".") == 2
