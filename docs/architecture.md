# Architecture

How Reel is put together. This page is written for someone who has never seen the repo.

## The one-paragraph version

Reel is a local HTTP proxy. Your application's LLM SDK (OpenAI, Anthropic, Gemini, raw `httpx`, LangChain, etc.) is configured to send requests to `http://127.0.0.1:7878` instead of `api.openai.com`. In **record** mode Reel forwards the request to the real provider and writes the full request/response exchange — including timed SSE chunks — into an append-only JSONL **cassette**. In **replay** mode Reel matches incoming requests against the cassette and serves the cached response without ever touching the network. **Auto** mode does the right thing per-request: replay if there's a match, record if there isn't.

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

| Module | Responsibility |
|---|---|
| `proxy/` | Async HTTP server, request/response forwarding, SSE streaming, mode dispatch (`record` / `replay` / `auto`) |
| `adapters/` | Provider-specific request fingerprinting and response normalization: `openai.py`, `anthropic.py`, `gemini.py` |
| `cassette/` | JSONL read/write, schema, matching engine (`exact` / `normalized` / `ignore-fields` / `fuzzy`) |
| `redact/` | Secret + PII scrubbing on capture and post-hoc |
| `cli/` | The `typer`-based CLI |
| `sdk/` | The `@cassette` decorator + pytest plugin |

## Three operating modes

### `record`

Every request is forwarded upstream. The full exchange — request, response, and (if streaming) timed chunks — is appended to the cassette. Use this for first-pass capture and refresh.

### `replay`

Requests are matched against the cassette and served locally. A cache miss returns HTTP 404 — a loud failure beats a silent regression. Use this in CI.

### `auto`

Replay if there's a match; record if there isn't. The default for local dev loops.

## Cassette format

One call per line. Plain JSONL.

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

JSONL was chosen because cassettes need to be:

- **Diff-friendly** in PRs — line-level reviews
- **Greppable** without parsing JSON
- **Append-safe** — no rewrite-the-world on record
- **Splittable** — large cassettes can be sharded by test name

A first line beginning with `{"_meta": {...}}` is reserved for per-cassette config (e.g. match-mode override).

## Streaming fidelity

For SSE responses:

- During capture, every `data: ...\n\n` frame is timestamped relative to the first byte of the response.
- During replay, frames are emitted with `asyncio.sleep` between them so TTFT and inter-chunk gaps mirror the original.
- Three timing modes are exposed on the CLI (`--timing`): `realtime` (default), `fast` (no sleeps), `slow=<N>` (chaos testing).

This matters because behavior under load — timeouts, partial buffering, race conditions in agent loops — depends on TTFT and inter-chunk gaps, not just the final text.

## Request matching

Different test contexts need different strictness:

| Mode | Behavior |
|---|---|
| `exact` | Byte-for-byte request equality |
| `normalized` (default) | Whitespace + JSON-key-order normalized before comparison |
| `ignore-fields` | User specifies fields to skip (e.g. `request_id`, timestamps) |
| `fuzzy` | Embedding-similarity on prompt text (optional `reel[fuzzy]` install) |

Per-cassette config lives in the optional first-line `_meta` entry, so once a cassette picks a mode every replay honors it.

## Provider adapters

Each adapter implements a small interface:

- **Fingerprint a request** — compute a stable hash over the bytes that matter (model, messages, tools, stream flag) while ignoring fields that drift between identical-in-intent calls (whitespace, key order).
- **Identify a response shape** — non-stream vs. SSE vs. server-sent JSON line stream (Gemini).
- **Surface a `provider` tag** on captured entries.

This is where the per-provider quirks live. Everything outside `adapters/` is provider-agnostic.

## Redaction

Two layers run on every captured response:

1. **Secret scrub** — regex patterns for OpenAI / Anthropic / Google / GitHub / AWS / Slack key shapes and Bearer tokens.
2. **PII scrub** — emails and phone numbers (default on; opt out with `REEL_REDACT_PII=0`).

Request headers are never serialized. API keys live there, and Reel drops them by design.

The `reel redact` CLI re-runs both passes on an existing cassette. The repo-local `pre-commit-cassette-check.py` hook refuses to commit any `*.jsonl` whose staged content still matches a secret pattern.

## Non-goals

- **Not an eval framework.** Reel records facts; it doesn't grade outputs.
- **Not an observability platform.** Reel works against local JSONL. Ship cassettes to your store of choice for dashboards.
- **Not inference.** Reel never generates tokens itself.
- **No telemetry, ever.**

## Source

See [`ARCHITECTURE.md`](https://github.com/tathagat22/reel/blob/main/ARCHITECTURE.md) in the repo for the canonical version of this document.

## Next

- [Roadmap](roadmap.md)
- [CLI reference](cli.md)
