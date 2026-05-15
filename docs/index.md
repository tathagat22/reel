---
title: "Reel — VCR for LLM APIs (OpenAI, Anthropic, Gemini)"
description: "Record OpenAI, Anthropic, and Gemini API calls once, replay them in tests and CI forever. Free, deterministic, SSE streaming-aware. The VCR.py / pytest-recording / respx alternative built specifically for LLMs."
---

# Reel — VCR for LLM APIs

**Record real calls to OpenAI, Anthropic, and Gemini once, then replay them deterministically in tests, CI, and your local dev loop — for free, forever.** No mocks. No SDK changes. No real network in CI. No surprise bills.

<video src="demos/reel-demo.mp4" controls muted loop playsinline preload="metadata" style="width:100%;max-width:900px;border-radius:8px;display:block;margin:1.5rem 0;"></video>

Reel is a local HTTP proxy that sits between your code and the LLM provider. On first call it forwards upstream and captures the wire-level request/response. On every call after, it replays from disk in ~3 ms. Cassettes are plain JSONL — you can `grep` them, `jq` them, `git diff` them in PRs. Secrets and PII are scrubbed at capture time.

[Install and record your first cassette in 5 minutes :material-arrow-right:](getting-started.md){ .md-button .md-button--primary }
[GitHub repo :material-github:](https://github.com/tathagat22/reel){ .md-button }

---

## Why this exists

**LLM tests are flaky and expensive.** A pytest suite that calls `OpenAI().chat.completions.create(...)` in 40 tests bills real money on every CI run — multiply by every PR push, every retry, every contributor. With Reel: record once locally, commit the cassette, run CI with `pytest --reel-mode replay` for $0.

**Production bugs in LLM responses are impossible to reproduce.** A user reports a weird answer; you have logs but no way to replay the exact call from a different machine. Reel cassettes are portable byte-for-byte recordings of what the upstream actually returned.

**Prompt iteration burns tokens on every tweak.** A two-hour prompt-engineering session might re-spend the same prompt 100 times. Reel makes each unique prompt cost real money exactly once.

**AI coding agents are slow.** Aider, opencode, Claude Code, Cursor, Codex CLI — most of them send the same file context, tool definitions, and embeddings to the LLM many times during a session. Reel caches the deterministic parts.

## 30-second demo

```bash
# 1. Install
pip install reel-vcr

# 2. Start Reel in auto mode (records first time, replays after)
reel auto --cassette tests/cassettes/quickstart.jsonl &

# 3. Point your SDK at it
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
export OPENAI_API_KEY=sk-...   # real key — Reel forwards it on first run only

# 4. Run your code. First run records. Every run after replays.
python my_app.py
```

That's it. The cassette is plain JSONL:

```json
{"id":"req_01","provider":"openai","endpoint":"/v1/chat/completions",
 "request":{"model":"gpt-5","messages":[...]},
 "response":{"status":200,"body":{...}}}
```

Diff cassettes in PRs. Grep them. Share them. They're regular files.

## How Reel compares

| Tool | Layer | Non-Python clients? | SSE streaming? | Survives SDK transport swaps? |
|---|---|---|---|---|
| **Reel** | HTTP proxy | ✅ Yes (any language) | ✅ With timing fidelity | ✅ Yes — transport-agnostic |
| VCR.py / pytest-recording / pytest-vcr | Monkey-patches `urllib3` / `requests` | ❌ Python only | Partial | ❌ Breaks when SDK changes transport |
| respx / pytest-httpx | Mocks `httpx` clients | ❌ Python only | Limited | ❌ Coupled to httpx |
| llm-test-harness | Wraps the SDK in Python (`harness.wrap(...)`) — bundles eval scoring | ❌ Python only | Limited | ❌ Coupled to specific SDK clients |
| agent-vcr | Records JSON-RPC for MCP servers (different layer entirely) | n/a — MCP, not LLM HTTP | n/a | n/a |
| WireMock / MockServer | HTTP proxy (Java) | ✅ Yes | Manual fixtures | ✅ Generic, not LLM-aware |
| Hand-rolled mocks | Inside your code | ❌ | Whatever you write | ❌ Whenever you forget to update them |

The trade-off: **VCR.py is easier to drop into a single test in a single file. Reel is easier to use across a whole project and any client that respects the standard `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` env-var convention** — including non-Python clients like Cursor and Aider.

## What works today

- **OpenAI, Anthropic, Gemini** HTTP APIs with path-based routing on a single proxy port
- **Any OpenAI-compatible upstream**: Ollama, NVIDIA NIM, vLLM, LM Studio, Groq, Together, OpenRouter
- Three modes: `record`, `replay`, `auto`
- **SSE streaming** captured chunk-by-chunk with millisecond timing fidelity (`--timing realtime | fast | slow=N`)
- **Smart matching**: `exact`, `normalized`, `ignore-fields`, `fuzzy` (sentence-transformers cosine similarity)
- **Capture-time redaction** of API keys, Bearer tokens, AWS keys, GitHub PATs, emails, US phone numbers
- **First-class pytest plugin** — `pytest --reel-mode replay` for zero-network CI
- **Analytics CLI** — `reel inspect / cost / diff / stats / doctor`
- **Local web inspector** — `reel ui` for browsing cassettes in a browser (Starlette + HTMX, no JS build step)
- **Pre-commit hook** that refuses to commit cassettes still containing detectable secret patterns

## Get started

[Install and record your first cassette in 5 minutes :material-arrow-right:](getting-started.md){ .md-button .md-button--primary }

Or jump to a specific topic:

- [Add Reel to a pytest suite in 60 seconds](guides/pytest.md)
- [Use replay mode in CI](guides/ci.md)
- [Run all three providers off one proxy](guides/multi-provider.md)
- [Keep secrets out of committed cassettes](guides/redaction.md)
- [CLI reference](cli.md)
- [Architecture overview](architecture.md)
- [Roadmap](roadmap.md)

## Frequently asked

**Is this just VCR.py with extra steps?**
No. VCR.py monkey-patches Python HTTP clients. When OpenAI or Anthropic ship a new SDK with a different transport, VCR.py silently breaks. Reel is an HTTP proxy — it sees the actual bytes on the wire, language-agnostic, SDK-agnostic.

**How is Reel different from `llm-test-harness` and `agent-vcr`?**
`llm-test-harness` wraps the SDK at the Python client level and bundles eval scoring — same Python-only / SDK-coupled shape as VCR.py. Reel sits one layer below as a language-agnostic HTTP proxy, and stays out of eval/scoring on purpose. `agent-vcr` records JSON-RPC for **MCP** servers (a different layer entirely) — it's complementary to Reel, not competitive: cassette your MCP tool servers with agent-vcr, cassette the LLM calls underneath with Reel.

**Will it work with Claude Code, Aider, opencode, Cursor, Codex CLI?**
Yes. All of them respect the standard `OPENAI_API_BASE` / `ANTHROPIC_BASE_URL` env-var convention. Cursor needs one settings-file line. Verified live with Claude Code, opencode, and Aider.

**What about API keys in committed cassettes?**
Reel never captures request headers — that's where keys live. Response bodies are scanned for `sk-*`, `sk-ant-*`, `AIza*`, `ghp_*`, `AKIA*`, and Bearer-token patterns; matches are redacted before write. A bundled pre-commit hook refuses to commit cassettes still containing detectable secrets.

**Does it work with local models — Ollama, vLLM, LM Studio?**
Yes. Anything OpenAI-compatible. Even with local models the win is real: replay is ~3 ms while local inference is 200-2000 ms.

**Why `pip install reel-vcr` but `import reel`?**
Bare `reel` on PyPI was taken by an unrelated async-subprocess library. Same convention as Pillow (`pip install pillow` → `import PIL`).

**Is there a Reel Cloud?**
No, and no plan to build one until there's clear pull. Runs entirely on `127.0.0.1`, zero telemetry, no phone-home, Apache 2.0.

More questions: [GitHub Discussions](https://github.com/tathagat22/reel/discussions) · [Open an issue](https://github.com/tathagat22/reel/issues)
