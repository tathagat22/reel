# Reel

[![CI](https://github.com/tathagat22/reel/actions/workflows/ci.yml/badge.svg)](https://github.com/tathagat22/reel/actions/workflows/ci.yml)
[![docs](https://github.com/tathagat22/reel/actions/workflows/docs.yml/badge.svg)](https://tathagat22.github.io/reel/)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11_|_3.12_|_3.13-blue.svg)](pyproject.toml)

**VCR for LLM APIs.** Record real OpenAI / Anthropic / Gemini calls once, replay them deterministically forever — including streaming, tool calls, and timing. **No SDK changes. No real network in CI. No surprise spend.**

> Docs: **<https://tathagat22.github.io/reel/>**

---

## The 30-second pitch

```bash
# Start once
uv run reel auto -c tape.jsonl

# Point any LLM SDK at the proxy
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1

# Run your code — first run records, every run after replays in ~3ms with $0 spend
python my_app.py
```

That's the entire workflow. The cassette is plain JSONL: diff it in PRs, grep it, share it. Secrets and PII are scrubbed at capture time, so it's safe to commit.

```text
your code  ─►  127.0.0.1:7878  ─►  reel proxy  ─►  api.openai.com
                                       │
                                       ├── writes JSONL on first call
                                       └── replays on next calls
```

## Why people pick it up

| Pain | What Reel does about it |
|---|---|
| `pytest` burns $$ on every CI run | Replay mode — zero network, no API key needed |
| Prompt iteration is slow + expensive | Captured responses replay in ~3ms; iterate the prompt locally for free |
| Production bug, no way to repro locally | Hand a colleague the JSONL — they replay your prod traffic byte-for-byte |
| Three providers, three mock libraries | One proxy serves OpenAI, Anthropic, and Gemini, including SSE streaming |

## Quickstart

```bash
git clone https://github.com/tathagat22/reel && cd reel && uv sync
uv run reel auto -c demo.jsonl &
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
python -c "from openai import OpenAI; print(OpenAI().chat.completions.create(model='gpt-5', messages=[{'role':'user','content':'Hi'}]).choices[0].message.content)"
```

PyPI + Homebrew land at the v0.1 cut. Until then, install from source.

### Drop into an existing pytest suite

```python
# tests/test_chatbot.py
def test_summarize(reel_cassette):       # ← that's the entire integration
    from openai import OpenAI
    OpenAI().chat.completions.create(...)
```

The pytest plugin auto-registers; **no conftest.py edits needed**. First run records to `tests/cassettes/test_chatbot/test_summarize.jsonl`; subsequent runs replay it.

```bash
pytest                           # first time: records (costs real money)
pytest                           # every time after: replays (free, ~3ms)
pytest --reel-mode replay        # CI mode — fails loud on uncaptured calls
```

Full guide: [docs/guides/pytest.md](docs/guides/pytest.md).

## Commands

| Command | What it does |
|---|---|
| `reel auto -c <path>` | Replay if cached, else record (the dev-loop default) |
| `reel record -c <path>` | Always forward + capture (initial capture, refresh) |
| `reel replay -c <path>` | Cassette only; 404 on miss (CI mode) |
| `reel ui -c <path>` | Local web UI to browse and search cassettes |
| `reel inspect -c <path>` | Rich-table view of entries, with composable filters |
| `reel cost -c <path>` | $$ aggregate — what you spent (or would have) |
| `reel diff -l A -r B` | Show drift between two cassettes |
| `reel stats -c <path>` | Counts, error rate, token totals, TTFT distribution |
| `reel redact -c <path>` | Post-hoc scrub secrets / PII |
| `reel doctor` | Health check: ports, upstreams, write perms |
| `reel version` | Print the installed version |

## What's in the box

- **OpenAI / Anthropic / Gemini** — single proxy, routed by path or explicit `/<provider>/…` URL prefix
- **SSE streaming with timing fidelity** — chunks captured per-ms; replay reproduces TTFT and inter-chunk gaps; `--timing realtime | fast | slow=N`
- **Four match modes** — `exact`, `normalized` (default), `ignore-fields` (great for per-call `request_id`), `fuzzy` (embedding similarity, optional `reel[fuzzy]`)
- **Capture-time redaction** — OpenAI / Anthropic / Google / GitHub / AWS / Slack key shapes + Bearer tokens, always. PII (email + phone) on by default; opt out with `REEL_REDACT_PII=0`
- **pytest plugin** — auto-discovered via `pytest11` entry point; `reel_cassette` fixture / `@cassette` decorator / `@pytest.mark.cassette`
- **Analytics CLI** — inspect / cost / diff / stats with composable filters and pricing tables for the major models
- **Structured logs** — `--log-format json` for `jq`-pipeable per-request observability
- **JSONL cassettes** — git-friendly, append-only, ~5 KB per buffered call
- **Pre-commit hook** to refuse any cassette that contains a detectable secret
- **344 tests** including multi-provider E2E + a pytester-driven plugin suite

## Architecture

```
src/reel/
├── proxy/        # HTTP + SSE core (forwarder, modes, stream, logs)
├── adapters/     # openai · anthropic · gemini (one ProviderAdapter interface)
├── cassette/     # schema · writer · reader · matcher · body codec · store
├── redact/       # secret + PII scrubbing
├── analytics/    # filters · cost · diff · stats (pure over CassetteEntry)
├── inspector/    # `reel ui` — Starlette + HTMX + Pico.css
├── cli/          # typer commands wired into `reel` entry point
└── sdk/          # @cassette decorator + pytest plugin
```

Deeper dive: [docs/architecture.md](docs/architecture.md). Roadmap: [docs/SPRINT_SHEET.md](docs/SPRINT_SHEET.md).

## Status

Sprints 1-6 of 6 are shipped. Currently pre-alpha — usable today from source, **PyPI publish + v0.1.0 tag** is the last open item.

## Development

```bash
uv sync
make check         # ruff + pyright (strict) + pytest — must pass before every commit
uv run reel auto -c ./scratch/test.jsonl
```

CI runs lint + format + typecheck + tests on Python 3.11 / 3.12 / 3.13 — see [.github/workflows/ci.yml](.github/workflows/ci.yml). Docs deploy to GitHub Pages — [.github/workflows/docs.yml](.github/workflows/docs.yml).

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The pre-commit hook will refuse any cassette with a detectable secret, so capture won't silently leak.

## License

[Apache 2.0](LICENSE)
