# Reel — AI Sprint Sheet

> Working document. Update task statuses as we ship. Tick boxes when DoD met.

## Legend

- `[ ]` pending
- `[~]` in progress
- `[x]` done

---

## Sprint 0 — Foundation *(1 day)*

**Goal:** Repo exists, structure is right, CI runs, contributor-ready.

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 0.1 | Init repo, Apache 2.0 LICENSE, .gitignore, README skeleton | LICENSE, .gitignore, README.md | Repo opens, license present | `[x]` |
| 0.2 | Python project scaffold using `uv` | pyproject.toml, src/reel/__init__.py, uv.lock | `uv sync` works on fresh clone | `[x]` |
| 0.3 | Directory layout (proxy/, adapters/, cassette/, redact/, cli/, sdk/) | Empty `__init__.py`s | `tree src/reel` matches spec | `[x]` |
| 0.4 | Dev tooling: ruff, pyright, pytest, pre-commit, Makefile | Configs in repo, `make check` passes | All tools run clean | `[x]` |
| 0.5 | GitHub Actions CI (lint + types + tests, py 3.11/3.12/3.13) | `.github/workflows/ci.yml` | CI green on first push | `[x]` |
| 0.6 | `ARCHITECTURE.md` with proxy + adapter + cassette diagram | One-page doc | Doc committed | `[x]` |
| 0.7 | `CONTRIBUTING.md` + `CODE_OF_CONDUCT.md` | Both files | Linked from README | `[x]` |
| 0.8 | Sprint sheet authored as the working source of truth | `docs/SPRINT_SHEET.md` | Future contributors follow it | `[x]` |

---

## Sprint 1 — Core Proxy + OpenAI (non-streaming) *(week 1)*

**Goal:** Proxy + record + replay works end-to-end for OpenAI `chat/completions` without streaming.

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 1.1 | Bare async HTTP proxy on `:7878` using starlette + httpx | `proxy/server.py` | `curl localhost:7878/health` → 200 | `[x]` |
| 1.2 | Upstream routing config (env-driven) | `proxy/router.py` | Unknown path 404s cleanly | `[x]` |
| 1.3 | OpenAI adapter — request fingerprint (model + messages + tools hash) | `adapters/openai.py` | Hash stable on whitespace, sensitive on content | `[x]` |
| 1.4 | Cassette writer (JSONL append) per schema | `cassette/writer.py` | Round-trip write → read works | `[x]` |
| 1.5 | Cassette reader + exact-match lookup | `cassette/reader.py`, `cassette/matcher.py` | Two identical requests match | `[x]` |
| 1.6 | `record` mode: forward + capture + write | `proxy/modes/record.py` | E2E: mock upstream call recorded | `[x]` |
| 1.7 | `replay` mode: serve from cassette only, 404 on miss | `proxy/modes/replay.py` | Recorded request replays without network | `[x]` |
| 1.8 | `auto` mode: replay if match, else record | `proxy/modes/auto.py` | Mode switching mid-session works | `[x]` |
| 1.9 | CLI: `reel record / replay / auto` | `cli/main.py` | `reel --help` shows commands | `[x]` |
| 1.10 | E2E tests using mock upstream (no real API in CI) | `tests/e2e/test_openai_basic.py` | CI passes without API key | `[x]` |
| 1.11 | Quickstart in README: 4 commands → working replay | README updated | New user runs it in <2 min | `[x]` |

**Sprint 1 DoD:** `pipx install reel && reel auto` works against any OpenAI SDK pointed at `localhost:7878`.

---

## Sprint 2 — Streaming *(week 2)* — *the hard week*

**Goal:** SSE streams record and replay with byte-perfect content and realistic timing.

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 2.1 | SSE parser (read `data: ...\n\n` frames) | `proxy/sse.py` | Unit tests on OpenAI sample stream | `[x]` |
| 2.2 | SSE forwarder: stream chunks live while capturing | `proxy/stream.py` | No buffering — chunks arrive live | `[x]` |
| 2.3 | Capture each chunk's wall-clock offset from first byte | Updated cassette schema | TTFT + inter-chunk gaps preserved | `[x]` |
| 2.4 | Streaming cassette entry shape (`stream_chunks: [{delta, t_offset_ms}]`) | Schema updated | New cassettes validate | `[x]` |
| 2.5 | Streaming replay: emit with `asyncio.sleep(offset)` | `proxy/modes/replay.py` | Replay TTFT within ±20ms | `[x]` |
| 2.6 | Timing modes: `realtime`, `fast`, `slow Nx` | CLI flag `--timing` | Tests for each mode | `[x]` |
| 2.7 | Handle stream interruptions / client disconnects | Error paths | No zombie tasks, no half-written cassettes | `[x]` |
| 2.8 | E2E: real OpenAI streaming → record → replay → assert chunks equal | `tests/e2e/test_streaming.py` | Passes locally | `[x]` |
| 2.9 | Demo GIF: pytest going from $5 → $0 with `--cassette` | `docs/demos/streaming.gif` | Embedded in README | `[ ]` *(deferred — manual recording)* |

**Sprint 2 DoD:** Streaming replay is indistinguishable from a real call (timing + content).

---

## Sprint 3 — Multi-provider + Matching + Redaction *(week 3)*

**Goal:** Anthropic + Gemini work. Matching is smart. Secrets are safe.

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 3.1 | Generic `ProviderAdapter` interface | `adapters/base.py` | OpenAI adapter refactored onto interface | `[ ]` |
| 3.2 | Anthropic adapter — messages + SSE | `adapters/anthropic.py` | Record+replay non-stream and stream | `[ ]` |
| 3.3 | Gemini adapter — generateContent + streamGenerateContent | `adapters/gemini.py` | Record+replay non-stream and stream | `[ ]` |
| 3.4 | Smart matcher: `exact`, `normalized`, `ignore-fields`, `fuzzy` | `cassette/matcher.py` | Each mode has tests | `[ ]` |
| 3.5 | Cassette-level match config | Schema + parser | Config respected on replay | `[ ]` |
| 3.6 | Secret redactor (regex for `sk-...`, `Bearer`, key shapes) | `redact/secrets.py` | Cassette never contains live keys | `[ ]` |
| 3.7 | PII redactor (emails, phone numbers, configurable) | `redact/pii.py` | Default-on, opt-out flag | `[ ]` |
| 3.8 | `reel redact <cassette>` post-hoc | CLI command | Round-trip preserves shape | `[ ]` |
| 3.9 | Pre-commit hook template (refuse secret-tainted cassettes) | `hooks/pre-commit-cassette-check` | Documented in README | `[ ]` |

**Sprint 3 DoD:** Same proxy serves three providers. Cassettes are safe to commit by default.

---

## Sprint 4 — Test framework integration *(week 4)*

**Goal:** One decorator to add Reel to any pytest suite.

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 4.1 | `@cassette(path)` decorator for pytest | `sdk/decorator.py` | Starts proxy per-test, isolated cassettes | `[ ]` |
| 4.2 | Pytest plugin (fixtures, env injection, cleanup) | `sdk/pytest_plugin.py`, entry point | `pytest tests/` works in any project | `[ ]` |
| 4.3 | First-run auto-record (CI-safe flag) | Env `REEL_RECORD_ON_MISSING=1` | Two-mode test loop works | `[ ]` |
| 4.4 | Cassette path conventions | `sdk/paths.py` | Tests find cassettes automatically | `[ ]` |
| 4.5 | Examples folder: openai-sdk, anthropic-sdk, langchain, instructor, dspy | `examples/*/test_*.py` | `pytest -q` green per example | `[ ]` |
| 4.6 | Docs: "Add Reel in 60 seconds" | `docs/guides/pytest.md` | Step-by-step | `[ ]` |

**Sprint 4 DoD:** A user adds Reel to their existing pytest project in <5 minutes.

---

## Sprint 5 — CLI polish + observability *(week 5)*

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 5.1 | `reel inspect <cassette>` (rich pretty-print) | CLI command | Readable, scannable | `[ ]` |
| 5.2 | `reel inspect --filter` (provider, model, has-tool-call, regex) | CLI flags | All filters tested | `[ ]` |
| 5.3 | `reel cost <cassette>` | `analytics/cost.py`, `pricing.json` | Prices current | `[ ]` |
| 5.4 | `reel diff <a> <b>` | CLI command | Model/response/cost deltas | `[ ]` |
| 5.5 | `reel stats <cassette>` (TTFT dist., tokens, errors) | CLI command | Useful summary | `[ ]` |
| 5.6 | Structured JSON logs (`--log-format json`) | Logging refactor | Pipeable to jq | `[ ]` |
| 5.7 | `reel doctor` | CLI command | Ports, upstream, write perms | `[ ]` |

**Sprint 5 DoD:** Power users can debug a flaky LLM test in <1 minute using the CLI alone.

---

## Sprint 6 — Web inspector + Launch *(week 6)*

| ID | Task | Deliverable | DoD | Status |
|----|------|-------------|-----|--------|
| 6.1 | Web inspector backend (`reel ui` on `:7879`) | `inspector/server.py` | Lists / loads / displays | `[ ]` |
| 6.2 | Web inspector frontend (HTMX + Pico.css, no SPA) | `inspector/templates/` | Loads <500ms | `[ ]` |
| 6.3 | Search & filter in UI | UI components | Works on 10k entries | `[ ]` |
| 6.4 | Docs site (mkdocs-material, dark mode, search) | `docs/` on GH Pages | Deployed | `[ ]` |
| 6.5 | Landing page (hero, video, install) | `docs/index.md` | Mobile + desktop | `[ ]` |
| 6.6 | 60-sec demo video | Embedded | Linked in launch posts | `[ ]` |
| 6.7 | Launch posts (HN, Twitter, Bluesky, Reddit) drafts | `marketing/launch/*.md` | Ready to copy-paste | `[ ]` |
| 6.8 | Newsletter outreach list | `marketing/outreach.csv` | 10+ contacts | `[ ]` |
| 6.9 | Maintainer outreach (LangChain, LlamaIndex, instructor, dspy, AI SDK) | DMs/issues drafted | 5+ sent on launch day | `[ ]` |
| 6.10 | PyPI + Homebrew formula | Packages published | Install works from clean env | `[ ]` |

**Sprint 6 DoD:** Launch day ships. Installable, demoable, discoverable.

---

## Cross-cutting (every sprint)

| ID | Task | Cadence |
|----|------|---------|
| X.1 | All PRs: tests + types + lint pass | Always |
| X.2 | Feature changes update README | Always |
| X.3 | End of sprint: tag version, write CHANGELOG | End of sprint |
| X.4 | CI scans cassettes for secrets | Every commit |
| X.5 | Proxy adds <2ms p99 overhead on non-stream paths | Sprint 3+ |

---

## Post-launch backlog (not in MVP)

- TypeScript SDK + vitest plugin
- Tool-call multi-turn matching (agent loops)
- Auto-instrumentation: LangChain, LlamaIndex, AI SDK
- Mutation testing: auto-fuzz captured prompts
- Snapshot mode (assert response shape, not content)
- Reel Cloud (team cassette sharing, hosted dashboard)
- Bedrock, Vertex, Azure OpenAI, Mistral, Groq, Cerebras, Together adapters
