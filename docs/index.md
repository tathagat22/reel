# Reel

**VCR for LLM APIs.** Record real calls to OpenAI / Anthropic / Gemini once, then replay them deterministically in tests — including streaming, tool calls, and timing.

No SDK lock-in. No real network in CI. No surprise spend.

<video src="demos/reel-demo.mp4" controls muted loop playsinline preload="metadata" style="width:100%;max-width:900px;border-radius:8px;display:block;margin:1.5rem 0;"></video>

---

## Why this exists

- **LLM tests are flaky and expensive.** Reel makes them deterministic and free.
- **Prompt debugging is opaque.** Reel shows you the exact bytes your app sent.
- **CI shouldn't cost money.** Reel runs your test suite with zero API spend.

## 30-second demo

```bash
# 1. Start the proxy in auto mode (records first time, replays after)
uv run reel auto --cassette tests/cassettes/quickstart.jsonl

# 2. Point your SDK at it
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
export OPENAI_API_KEY=sk-...   # real key — Reel forwards it on first run

# 3. Run your code. First run records. Every run after replays.
python my_app.py
```

That's it. Cassettes are plain JSONL — diff them in PRs, grep them, redact them.

```json
{"id":"req_01","provider":"openai","endpoint":"/v1/chat/completions",
 "request":{"model":"gpt-5","messages":[...]},
 "response":{"status":200,"body":{...}}}
```

## What works today

- **OpenAI / Anthropic / Gemini** HTTP APIs with path-based routing
- Three modes: `record`, `replay`, `auto`
- **SSE streaming** with millisecond timing fidelity
- **Smart matching**: `exact`, `normalized`, `ignore-fields`, `fuzzy`
- **Capture-time redaction** of API keys, Bearer tokens, emails, phone numbers
- **First-class pytest plugin** — `pytest --reel-mode replay` for zero-network CI
- **Analytics CLI** — `reel inspect / cost / diff / stats / doctor`

## Get started

[Install and record your first cassette in 5 minutes :material-arrow-right:](getting-started.md){ .md-button .md-button--primary }

Or jump to:

- [Add Reel to a pytest suite in 60 seconds](guides/pytest.md)
- [Use replay mode in CI](guides/ci.md)
- [Run all three providers off one proxy](guides/multi-provider.md)
- [Keep secrets out of committed cassettes](guides/redaction.md)
- [CLI reference](cli.md)
- [Architecture overview](architecture.md)
