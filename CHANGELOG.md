# Changelog

All notable changes to **Reel** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- SEO-friendly README and docs landing page — comparison table vs VCR.py / pytest-recording / respx, FAQ section, explicit support notes for Aider / opencode / Claude Code / Cursor / Codex CLI.
- Per-page meta descriptions across all docs pages (`getting-started`, `cli`, `architecture`, `roadmap`, and the four guides) for better search-engine snippets.

### Planned for v0.2
- `reel run -- <cmd>` — wrapper that spawns the proxy for the lifetime of a single subprocess, so `reel run -- claude` and `reel run -- aider` work with zero terminal setup.
- `reel up` / `reel down` / `eval "$(reel env)"` — zero-config onboarding that sets/unsets `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `GEMINI_BASE_URL` automatically.
- Transparent embedding-cache mode — dedupe `/v1/embeddings` calls across runs.
- Multi-turn agentic tool-loop matching (currently each call records correctly, but order-of-operations across long loops needs work).
- First-class adapters for Azure OpenAI, AWS Bedrock, and GCP Vertex (today they work as generic upstreams).

## [0.1.0] — 2026-05-15

First public release on PyPI as [`reel-vcr`](https://pypi.org/project/reel-vcr/).

### Added — proxy core

- HTTP proxy on `127.0.0.1:7878` built on Starlette + httpx + uvicorn.
- Three modes: `record`, `replay`, `auto` (replay if cached, else record).
- Provider adapters for **OpenAI** (`/v1/chat/completions`, `/v1/embeddings`, `/v1/responses`), **Anthropic** (`/v1/messages`), **Google Gemini** (`/v1beta/models/<model>:generateContent` and `:streamGenerateContent`).
- Path-prefix routing — one proxy can serve all three providers simultaneously via `/openai/v1/...`, `/anthropic/v1/...`, `/gemini/v1beta/...`.
- Generic OpenAI-compatible passthrough for Ollama, NVIDIA NIM, vLLM, LM Studio, Groq, Together, OpenRouter (set `--upstream` to whichever URL they serve).
- **SSE streaming capture** with chunk-by-chunk wall-clock offsets, replayed with `asyncio.sleep`-based timing fidelity (within ~20 ms of original). Three timing modes: `--timing realtime | fast | slow=<N>`.

### Added — cassette format

- JSONL cassette schema (one entry per LLM call) — plain text, diff-friendly, grep-friendly, git-friendly.
- Fingerprint matcher using sha256 of canonicalized JSON body + endpoint + method.
- Four matcher modes: `exact`, `normalized`, `ignore-fields`, `fuzzy` (sentence-transformers cosine similarity for prompt drift).
- In-memory cassette store with O(1) fingerprint lookup.

### Added — security

- Capture-time redaction of API keys (`sk-*`, `sk-ant-*`, `AIza*`, `ghp_*`, `AKIA*`), Bearer tokens, AWS keys, GitHub PATs.
- PII regex scrubbing (emails, US phone numbers).
- **Request headers are never captured** — that's where keys live in every supported provider.
- Pre-commit hook (`hooks/pre-commit-cassette-check.py`) that refuses to commit any cassette containing a remaining detectable secret pattern.

### Added — pytest plugin

- Auto-registered via `pytest11` entry point — no `conftest.py` edits.
- `reel_cassette` fixture with auto-inferred cassette path from test name.
- `@cassette(path, mode=...)` decorator for explicit paths.
- `@pytest.mark.cassette(path, mode=...)` marker form.
- `pytest --reel-mode replay` global override — fails loud on uncaptured requests, for CI.

### Added — CLI

- `reel record` / `reel replay` / `reel auto` — proxy modes.
- `reel inspect` — Rich-table view with composable filters (`--provider`, `--model`, `--status`, `--has-tool-call`, `--match-regex`).
- `reel cost` — Token totals × current OpenAI / Anthropic / Gemini pricing → $ summary.
- `reel diff -l A -r B` — Aligned diff of two cassettes.
- `reel stats` — Counts, error rate, token totals, TTFT distribution.
- `reel redact` — Post-hoc scrub of an existing cassette.
- `reel doctor` — Sanity check: port availability, upstream reachability, write perms, optional-dep state.
- `reel ui` — Local web inspector (Starlette + HTMX + Pico.css, no JS build step) for browsing cassettes in a browser.
- `reel version`.

### Added — packaging

- PyPI package `reel-vcr` (bare `reel` was already taken by an unrelated async-subprocess library).
- CLI binary, GitHub repo, and Python import path all remain `reel`.
- Homebrew formula (`Formula/reel.rb`) targeting the `reel-vcr` sdist.
- mkdocs-material docs site auto-deploying to GitHub Pages on every push to `main`.

### Verified

- Clean `pip install` on Python 3.11, 3.13, and 3.14 — 102 install/import/runtime checks.
- 344 tests in the project's own suite, green on every CI run.
- Live integration with Aider, opencode, and Claude Code (via `ANTHROPIC_BASE_URL`).

### Known limitations

- Multi-turn agentic tool-call loops: each individual call is captured correctly, but order-of-operations matching across long loops needs work.
- Azure OpenAI / AWS Bedrock / GCP Vertex work as generic upstreams; first-class adapters with provider-specific smart-matcher ignore lists are on the v0.2 roadmap.

[Unreleased]: https://github.com/tathagat22/reel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tathagat22/reel/releases/tag/v0.1.0
