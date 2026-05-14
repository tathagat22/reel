# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnnecessaryCast=false
"""pytest plugin — registers the ``reel_cassette`` fixture and ``cassette`` marker.

Auto-discovered via the ``pytest11`` entry point declared in pyproject. No
``conftest.py`` setup required on the user side.

pytest's marker / node types are too loose for pyright strict mode; we
silence those rules at the file level rather than scatter casts.

Two usage shapes:

1. **Fixture only (recommended)** — the cassette path is inferred from the
   test name::

        def test_summarize(reel_cassette: ProxyHandle) -> None:
            client = OpenAI()  # OPENAI_BASE_URL points at reel_cassette.base_url
            ...

2. **Marker for custom path or mode**::

        @pytest.mark.cassette("path/to/tape.jsonl", mode="record")
        def test_summarize(reel_cassette: ProxyHandle) -> None:
            ...

CLI overrides: ``--reel-mode {record,replay,auto}`` forces a mode for every
test in the session — useful for ``--reel-mode replay`` in CI.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from reel.proxy.config import Mode
from reel.sdk.cassette import ProxyHandle, proxy_context
from reel.sdk.paths import default_cassette_path


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("reel", "Reel — VCR for LLM APIs")
    group.addoption(
        "--reel-mode",
        action="store",
        default=None,
        choices=["record", "replay", "auto"],
        help="Override Reel mode for every reel_cassette fixture.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "cassette(path=None, mode='auto'): point a test at a Reel cassette",
    )


@pytest.fixture
def reel_cassette(request: pytest.FixtureRequest) -> Iterator[ProxyHandle]:
    """Per-test Reel proxy. Cassette path inferred unless overridden by marker."""
    node = request.node
    marker = node.get_closest_marker("cassette")

    custom_path: str | None = None
    custom_mode: Mode | None = None

    if marker is not None:
        if marker.args:
            custom_path = str(marker.args[0])
        custom_path = custom_path or marker.kwargs.get("path")
        marker_mode = marker.kwargs.get("mode")
        if marker_mode is not None:
            custom_mode = cast(Mode, marker_mode)

    path: Path = Path(custom_path) if custom_path else default_cassette_path(node)

    cli_mode_raw = request.config.getoption("--reel-mode")
    cli_mode = cast("Mode | None", cli_mode_raw)
    mode: Mode = cli_mode or custom_mode or "auto"

    with proxy_context(str(path), mode=mode) as handle:
        yield handle
