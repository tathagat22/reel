# Reel

**VCR for LLM APIs.** Record real calls to OpenAI / Anthropic / Gemini once, then replay them deterministically in tests — including streaming, tool calls, and timing. No SDK lock-in, no real network in CI, no surprise spend.

> Status: pre-alpha. Sprint 0 of 6 — see [`docs/SPRINT_SHEET.md`](docs/SPRINT_SHEET.md).

---

## Why

- **LLM tests are flaky and expensive.** Reel makes them deterministic and free.
- **Prompt debugging is opaque.** Reel shows you the exact bytes your app sent.
- **Production bugs are hard to reproduce.** Reel lets you replay a captured session locally.
- **CI shouldn't cost money.** Reel runs your test suite with zero API spend.

## How (30-second demo)

```bash
# 1. Install
pipx install reel

# 2. Start the proxy
reel auto --cassette tests/cassettes/my_test.jsonl

# 3. Point your app at it
export OPENAI_BASE_URL=http://localhost:7878

# 4. Run your code — first time records, every time after replays
python my_app.py
```

That's it. No SDK changes. No cloud signup. Cassettes are JSONL — diff them in PRs.

## Features

| | |
|---|---|
| ✅ | Works with **any** OpenAI / Anthropic / Gemini client (it's just an HTTP proxy) |
| ✅ | **Full streaming replay** with original chunk timing |
| ✅ | Tool calls captured and replayed across multi-turn |
| ✅ | Smart matching: exact / normalized / ignore-fields / fuzzy |
| ✅ | Secret + PII redaction by default |
| ✅ | First-class `pytest` plugin via `@cassette` decorator |
| ✅ | Cost & token analytics out of the box |
| ✅ | Single binary, Apache 2.0, no telemetry |

## Project layout

```
src/reel/
├── proxy/      # HTTP + SSE proxy core
├── adapters/   # openai.py, anthropic.py, gemini.py
├── cassette/   # read, write, match, redact
├── redact/     # secret + PII scrubbing
├── cli/        # `reel record | replay | auto | inspect | cost | diff`
└── sdk/        # @cassette decorator, pytest plugin
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the high-level design and [`docs/SPRINT_SHEET.md`](docs/SPRINT_SHEET.md) for the active roadmap.

## Contributing

PRs welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE)
