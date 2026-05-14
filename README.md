# Reel

[![CI](https://github.com/tathagat22/reel/actions/workflows/ci.yml/badge.svg)](https://github.com/tathagat22/reel/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11_|_3.12_|_3.13-blue.svg)](pyproject.toml)

**VCR for LLM APIs.** Record real calls to OpenAI / Anthropic / Gemini once, then replay them deterministically in tests — including streaming, tool calls, and timing. No SDK lock-in, no real network in CI, no surprise spend.

> Status: pre-alpha. **Sprints 1 + 2 + 3 of 6 are shipped** — OpenAI / Anthropic / Gemini record / replay / auto modes work end-to-end, including SSE streaming, smart-matcher modes (exact / normalized / ignore-fields / fuzzy), per-cassette match config, and capture-time secret + PII redaction. The pytest plugin lands in Sprint 4. See [`docs/SPRINT_SHEET.md`](docs/SPRINT_SHEET.md).

---

## Why

- **LLM tests are flaky and expensive.** Reel makes them deterministic and free.
- **Prompt debugging is opaque.** Reel shows you the exact bytes your app sent.
- **Production bugs are hard to reproduce.** Reel lets you replay a captured session locally.
- **CI shouldn't cost money.** Reel runs your test suite with zero API spend.

## Quickstart — under 2 minutes

### 1. Install

For now (pre-alpha), install from source:

```bash
git clone https://github.com/tathagat22/reel
cd reel
uv sync
uv run reel --help
```

PyPI + Homebrew formulas land in Sprint 6.

### 2. Start the proxy in `auto` mode

```bash
uv run reel auto --cassette tests/cassettes/quickstart.jsonl
```

You'll see:

```
reel 0.0.1 · mode=auto
  listen   http://127.0.0.1:7878
  upstream https://api.openai.com
  cassette tests/cassettes/quickstart.jsonl
```

### 3. Point your OpenAI SDK at the proxy

```bash
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
export OPENAI_API_KEY=sk-…   # your real key — Reel forwards it on first run
```

### 4. Run your code — first run records, every run after replays

```python
from openai import OpenAI
client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "Say hi"}],
)
print(resp.choices[0].message.content)
```

That's it. Run it once with internet — Reel forwards to OpenAI and captures the exchange. Run it again — Reel replays the cassette and never hits the network.

```bash
$ cat tests/cassettes/quickstart.jsonl
{"id":"req_…","ts":"2026-05-15T…","provider":"openai", …}
```

Cassettes are plain JSONL — diff them in PRs, grep them, redact them.

## Modes

| Command | What it does | When to use |
|---------|--------------|-------------|
| `reel auto -c <path>` | Replay if cached, else record | **Local dev (default)** |
| `reel record -c <path>` | Always forward + capture | First-pass capture / refresh |
| `reel replay -c <path>` | Cassette-only; 404 on miss | **CI** (no API key needed) |

## What works today (Sprints 1 + 2 + 3)

- **OpenAI / Anthropic / Gemini** HTTP APIs — path-based routing or explicit `/<provider>/...` URL prefix for unambiguous multi-provider use
- Three modes: `record`, `replay`, `auto`
- **SSE streaming** — chunks captured with millisecond timing; replay reproduces TTFT and inter-chunk gaps; `--timing realtime | fast | slow=<N>`
- **Smart match modes** — `exact`, `normalized` (default), `ignore-fields` for per-call `request_id`/`trace_id`, `fuzzy` (embedding similarity, optional `reel[fuzzy]` install)
- **Per-cassette match config** via an optional `_meta` line — pick a mode once, every replay honors it
- **Capture-time redaction** — secrets always scrubbed (OpenAI / Anthropic / Google / GitHub / AWS / Slack key shapes, Bearer tokens); PII (email + phone) scrubbed by default, opt out with `REEL_REDACT_PII=0`
- **`reel redact -c <file>`** to scrub existing cassettes post-hoc
- **Pre-commit hook** (`hooks/pre-commit-cassette-check.py`) refuses any staged JSONL containing a detectable secret
- Stable, provider-aware request fingerprinting (whitespace/key-order insensitive)
- JSONL cassettes (git-friendly, append-safe)
- API keys never captured — request headers are dropped by design
- 209+ tests including 3 multi-provider E2E suites

## What's coming

| Sprint | Lands |
|--------|-------|
| 4 | `pytest` plugin (`@cassette` decorator) |
| 5 | `reel inspect / cost / diff / stats / doctor` |
| 6 | Web inspector UI, docs site, PyPI, Homebrew, launch |

## Project layout

```
src/reel/
├── proxy/      # HTTP + SSE proxy core (proxy, forwarder, modes)
├── adapters/   # openai.py · anthropic.py · gemini.py (sprint 3)
├── cassette/   # schema, writer, reader, matcher, body codec, store
├── redact/     # secret + PII scrubbing (sprint 3)
├── cli/        # `reel record | replay | auto | inspect | cost | diff`
└── sdk/        # @cassette decorator + pytest plugin (sprint 4)
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design and [`docs/SPRINT_SHEET.md`](docs/SPRINT_SHEET.md) for the active roadmap.

## Development

```bash
uv sync
make check       # ruff + pyright + pytest — must pass before every commit
uv run reel auto -c ./scratch/test.jsonl
```

CI runs lint + typecheck + tests on Python 3.11 / 3.12 / 3.13 — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Contributing

PRs welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE)
