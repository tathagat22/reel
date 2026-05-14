"""Sprint 4.2 — pytest plugin: reel_cassette fixture, marker, CLI flags."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


def test_reel_cassette_fixture_is_available(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_uses_fixture(reel_cassette):
            assert reel_cassette.port > 0
            assert reel_cassette.base_url.startswith("http://127.0.0.1:")
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_default_cassette_path_lives_alongside_test_file(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_first(reel_cassette):
            assert reel_cassette.cassette_path.name == "test_first.jsonl"
            # Cassette lives under <test_file_dir>/cassettes/<test_file_stem>/
            parents = reel_cassette.cassette_path.parents
            assert parents[0].name == reel_cassette.cassette_path.parent.name
            assert parents[1].name == "cassettes"
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_marker_overrides_path(pytester: pytest.Pytester, tmp_path: Path) -> None:
    custom = tmp_path / "custom.jsonl"
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.cassette({str(custom)!r})
        def test_custom(reel_cassette):
            assert str(reel_cassette.cassette_path) == {str(custom)!r}
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_marker_overrides_path_via_kwarg(pytester: pytest.Pytester, tmp_path: Path) -> None:
    custom = tmp_path / "kwarg.jsonl"
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.cassette(path={str(custom)!r})
        def test_custom(reel_cassette):
            assert str(reel_cassette.cassette_path) == {str(custom)!r}
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_cli_mode_override(pytester: pytest.Pytester) -> None:
    """`--reel-mode replay` against an empty cassette should make calls 404."""
    pytester.makepyfile(
        """
        import os, httpx

        def test_replay_only_404s(reel_cassette):
            # The cassette is empty — replay-mode lookup must return 404.
            base = os.environ["OPENAI_BASE_URL"]
            r = httpx.post(
                f"{base}/chat/completions",
                json={"model": "gpt-5", "messages": []},
                timeout=2.0,
            )
            assert r.status_code == 404
        """
    )
    # Pre-create an empty cassette so replay mode has a file to open.
    cassettes_dir = pytester.path / "cassettes" / "test_cli_mode_override"
    cassettes_dir.mkdir(parents=True)
    (cassettes_dir / "test_replay_only_404s.jsonl").write_text("")

    result = pytester.runpytest("--reel-mode", "replay", "-v")
    result.assert_outcomes(passed=1)


def test_plugin_registers_marker(pytester: pytest.Pytester) -> None:
    """`pytest --markers` lists the 'cassette' marker."""
    result = pytester.runpytest("--markers")
    result.stdout.fnmatch_lines(["*cassette(path=None*"])
