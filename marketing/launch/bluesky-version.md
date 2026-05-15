# Bluesky thread

Bluesky caps posts at 300 characters. Audience skews developer / open-source / Python — lean heavier on technical detail and less on the "save money" framing than the Twitter version.

---

**1/**

Released Reel today — a local HTTP proxy that records OpenAI / Anthropic / Gemini calls into JSONL cassettes and replays them deterministically, streaming included.

Apache 2.0. Pre-alpha. 332 tests.

<REPO_URL>

---

**2/**

The shape: starlette + httpx proxy on `:7878`. Point your SDK at it, first run forwards upstream and captures, every run after replays from disk. SSE chunks keep their wall-clock offsets so TTFT and inter-chunk gaps survive replay.

---

**3/**

Why a proxy, not a Python wrapper? Because it works with anything that speaks HTTP — every SDK, every language, every framework on top (LangChain, LlamaIndex, dspy, instructor, your own). No monkey-patching, no per-SDK adapters in user code.

---

**4/**

Cassettes are plain JSONL. One entry per call. You diff them in PRs, grep them, `jq` them. A pre-commit hook refuses any cassette still carrying a detectable secret pattern. Keys + PII are scrubbed at capture time by default.

---

**5/**

Matcher modes for prompts that drift slightly:

- `exact` — bytes-for-bytes
- `normalized` (default) — whitespace + key-order tolerant
- `ignore-fields` — drop per-call `request_id`, `trace_id`, ...
- `fuzzy` — embedding similarity (opt-in extra)

---

**6/**

Pytest plugin is auto-registered via the `pytest11` entry point. Use the `@cassette` decorator, the `reel_cassette` fixture, or `@pytest.mark.cassette`. CI mode: `pytest --reel-mode replay` — any unmatched call 404s, no API key required, no possible spend.

---

**7/**

Analytics CLI on the side: `reel inspect / cost / diff / stats / doctor`. Cost uses current pricing tables for OpenAI / Anthropic / Gemini. `diff` shows what regressed between two cassettes. Logs are structured JSON (`--log-format json`) — `jq`-able.

---

**8/**

Built on starlette + uvicorn + httpx + pydantic v2 + typer. Strict ruff + pyright. CI on Python 3.11 / 3.12 / 3.13. PyPI + Homebrew land this sprint.

Feedback wanted — particularly on the matcher modes and the pytest plugin ergonomics.

<REPO_URL>
