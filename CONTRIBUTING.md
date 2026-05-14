# Contributing to Reel

First — thanks for showing up. Reel is small enough that one good PR meaningfully changes it.

## Quick start

```bash
git clone https://github.com/tathagat22/reel
cd reel
uv sync
make check       # lint + types + tests
```

You should see all checks pass on a clean clone. If not, open an issue immediately — that's a real bug.

## Workflow

1. Open an issue first for anything non-trivial (new feature, structural refactor). Tiny fixes can skip this.
2. Branch from `main`: `git checkout -b feat/short-name`.
3. Make the change, add tests, run `make check` locally.
4. Open a PR. Link the issue. Keep PRs focused — one concern at a time.

## Code style

- **Formatter:** `ruff format` (no debates).
- **Linter:** `ruff check` (strict).
- **Types:** `pyright` in strict mode. Public functions must be fully typed.
- **Async-first:** all I/O paths are async. Sync helpers only where it genuinely simplifies.
- **No telemetry, no analytics, no external network calls** outside of upstream LLM forwarding.

## Tests

- Unit tests for every new module.
- E2E tests using a mock upstream (`respx` or local fixture server) — **no live API keys in CI**.
- Integration tests that hit real APIs are marked `@pytest.mark.integration` and skipped by default.

## Cassettes in this repo

Test cassettes live under `tests/cassettes/`. They are **redacted by default** — Reel scrubs secrets (and PII unless opted out) on capture. If you ever need to scrub after the fact:

```bash
uv run reel redact -c tests/cassettes/your-new.jsonl
```

### Pre-commit guardrail

A repo-local hook at `hooks/pre-commit-cassette-check.py` refuses to commit any `*.jsonl` whose staged content contains a detectable secret pattern. Enable with:

```bash
uv run pre-commit install
```

It runs alongside ruff and the other built-in pre-commit checks.

## Commit messages

Conventional-ish. No strict format, but:

- `feat: add Anthropic streaming adapter`
- `fix: SSE chunk ordering on slow networks`
- `docs: clarify match modes`
- `chore: bump httpx to 0.28`

Keep messages focused on the *why*, not the *what* — the diff already shows the what.

## What's in / out of scope

**In scope:**
- Provider adapters (any LLM HTTP API)
- Better matching strategies
- Streaming-format support (SSE, WebSocket, future protocols)
- Test-framework integrations (pytest, vitest, jest, ...)
- CLI ergonomics

**Out of scope** (please don't propose):
- Eval frameworks
- Inference / fine-tuning
- Telemetry, analytics, "anonymous usage stats"
- Cloud-only features that don't work offline

## License

By contributing you agree your work is licensed under Apache 2.0 (the project's license). There is **no CLA**.
