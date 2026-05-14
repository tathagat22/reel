# Reel — Architecture

> Status: pre-alpha. This document tracks intent; reality lands per-sprint.

## One-paragraph summary

Reel is a local HTTP proxy that sits between any LLM client (OpenAI SDK, Anthropic SDK, raw `httpx`, LangChain, etc.) and the upstream provider. In **record** mode it forwards requests to the real API and captures every request/response (including SSE chunk timing) into an append-only JSONL **cassette**. In **replay** mode it serves responses from the cassette without ever touching the network. **Auto** mode replays when there's a match and records when there isn't. Provider differences (request shape, streaming format, tool-call schema) are isolated in `adapters/`. Everything else is provider-agnostic.

## High-level diagram

```
┌────────────┐   HTTP / SSE    ┌──────────────────────────┐   HTTP / SSE   ┌──────────────┐
│ Your app   │ ───────────────►│           Reel           │ ──────────────►│  OpenAI /    │
│ (any lang) │                 │     (local proxy :7878)  │                │  Anthropic / │
│            │ ◄───────────────│                          │ ◄──────────────│  Gemini      │
└────────────┘                 └──────────────────────────┘                └──────────────┘
                                          │
                          ┌───────────────┼────────────────┐
                          ▼               ▼                ▼
                   ┌────────────┐  ┌────────────┐   ┌────────────┐
                   │  adapters  │  │  cassette  │   │   redact   │
                   │ (per prov.)│  │ (JSONL r/w)│   │ (secrets,  │
                   │            │  │            │   │  PII)      │
                   └────────────┘  └────────────┘   └────────────┘
                          │               │                │
                          └──────────┬────┴────────────────┘
                                     ▼
                                ┌─────────┐
                                │   CLI   │  reel record | replay | auto | inspect | cost | diff
                                └─────────┘
```

## Modules

| Module | Responsibility | Status |
|--------|----------------|--------|
| `proxy/` | Async HTTP server, request/response forwarding, SSE streaming, mode dispatch (record/replay/auto) | Sprint 1–2 |
| `adapters/` | Provider-specific request fingerprinting and response normalization (`openai.py`, `anthropic.py`, `gemini.py`) | Sprint 1 (OpenAI), Sprint 3 (rest) |
| `cassette/` | JSONL read/write, schema, matching engine (exact / normalized / ignore-fields / fuzzy) | Sprint 1 |
| `redact/` | Secret + PII scrubbing on capture and post-hoc | Sprint 3 |
| `cli/` | `typer` CLI — `record`, `replay`, `auto`, `inspect`, `cost`, `diff`, `redact`, `doctor`, `ui` | Sprint 1+ |
| `sdk/` | `@cassette` decorator + pytest plugin (auto record-on-miss, replay-otherwise) | Sprint 4 |

## Three operating modes

1. **`record`** — every request is forwarded upstream; the request, response, and (if streaming) timed chunks are appended to a cassette. Useful for first-pass capture.
2. **`replay`** — requests are matched against the cassette and served locally. Cache-miss = HTTP 404 (loud failure beats silent regression).
3. **`auto`** — replay if there's a match, record if there isn't. The default for local dev loops.

## Cassette format (JSONL, one call per line)

```json
{
  "id": "req_01",
  "ts": "2026-05-15T10:23:11Z",
  "provider": "openai",
  "endpoint": "/v1/chat/completions",
  "request": {
    "model": "gpt-5",
    "messages": [...],
    "stream": true,
    "_hash": "sha256:..."
  },
  "response": {
    "status": 200,
    "stream_chunks": [
      {"delta": "Hello", "t_offset_ms": 142},
      {"delta": " world", "t_offset_ms": 198}
    ],
    "final": { ... }
  },
  "meta": {
    "tokens_in": 412,
    "tokens_out": 89,
    "cost_usd": 0.0021,
    "ttft_ms": 142,
    "total_ms": 890
  }
}
```

JSONL was chosen so cassettes are:
- **Diff-friendly** in PRs (line-level reviews)
- **Greppable** without parsing JSON
- **Append-safe** (no rewrite-the-world on record)
- **Splittable** (large cassettes can be sharded by test name)

## Streaming fidelity (the hard part)

For SSE responses:

- During capture, every `data: ...\n\n` frame is timestamped relative to the first byte of the response.
- During replay, frames are emitted with `asyncio.sleep` between them so TTFT and inter-chunk gaps mirror the original.
- Three timing modes: `realtime` (default), `fast` (no sleeps), `slow Nx` (chaos testing).

## Request matching

Different test contexts need different strictness:

| Mode | Behavior |
|------|----------|
| `exact` | Byte-for-byte request equality |
| `normalized` | Whitespace + JSON-key-order normalized before comparison (default) |
| `ignore-fields` | User specifies fields to skip (e.g., `request_id`, timestamps) |
| `fuzzy` | Embedding-similarity on prompt text (optional dep) |

Per-cassette config in a top-level `_meta` line.

## Non-goals

- **Not an eval framework.** Reel records facts; it doesn't grade outputs. Use Inspect / Promptfoo / Phoenix for evals.
- **Not an observability platform.** Reel works against local JSONL. Send the cassettes to your favorite store if you want dashboards.
- **Not inference.** Reel never generates tokens itself.
- **No telemetry, ever.**

## Future (post-MVP)

- TypeScript SDK + vitest plugin
- Tool-call mutation testing
- Auto-instrumentation packages for LangChain / LlamaIndex / AI SDK
- Optional hosted dashboard for team cassette sharing (Reel Cloud)
