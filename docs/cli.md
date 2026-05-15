---
title: "Reel CLI reference — record, replay, inspect, cost, diff, doctor"
description: "Complete CLI reference for the `reel` command — record / replay / auto proxy modes, plus inspect, cost, diff, stats, redact, doctor, and ui subcommands. Options, examples, exit codes."
---

# CLI reference

Every `reel` subcommand, its options, examples, and exit codes. Generated from `uv run reel --help` and cross-checked against `src/reel/cli/`.

## Overview

```
reel record   Forward every request upstream and capture into the cassette.
reel replay   Serve responses from the cassette only. 404 on miss; no network.
reel auto     Replay if cached, else record. Default for local dev.
reel inspect  Display a cassette's entries, filtered to your liking.
reel cost     Sum the token cost of every priced entry.
reel diff     Compare two cassettes and report what drifted.
reel stats    Summarize a cassette: counts, errors, tokens, TTFT distribution.
reel doctor   Diagnose a Reel install.
reel redact   Scrub secrets (and optionally PII) from a cassette.
reel version  Print the installed Reel version.
```

## Common options

These apply to every proxy command (`record`, `replay`, `auto`):

| Option | Default | Meaning |
|---|---|---|
| `--host`, `-h` | `127.0.0.1` | Bind address for the proxy |
| `--port`, `-p` | `7878` | TCP port |
| `--cassette`, `-c` | *(required)* | Path to the JSONL cassette |
| `--upstream` | `https://api.openai.com` | OpenAI-compatible upstream base URL |
| `--log-format` | `text` | Per-request log format: `text` or `json` |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic error |
| `2` | Usage error or required input missing (e.g. cassette file does not exist) |

---

## `reel record`

Forward every request upstream and append the captured exchange to the cassette.

### Synopsis

```bash
reel record --cassette <path> [--host HOST] [--port PORT] [--upstream URL] [--log-format FORMAT]
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--cassette`, `-c` *(required)* | — | JSONL cassette path (will be appended) |
| `--host`, `-h` | `127.0.0.1` | Bind address |
| `--port`, `-p` | `7878` | TCP port |
| `--upstream` | `https://api.openai.com` | Upstream base URL (OpenAI-compatible) |
| `--log-format` | `text` | `text` or `json` |

### Examples

```bash
# Capture every call into quickstart.jsonl
uv run reel record -c tests/cassettes/quickstart.jsonl

# Forward to a custom OpenAI-compatible endpoint
uv run reel record -c c.jsonl --upstream https://my-gateway.example.com

# JSON logs for piping into jq
uv run reel record -c c.jsonl --log-format json | jq .
```

---

## `reel replay`

Serve responses from the cassette only. A cache miss returns HTTP 404 — no upstream call is made. This is the right mode for CI.

### Synopsis

```bash
reel replay --cassette <path> [--host HOST] [--port PORT] [--upstream URL] [--timing MODE] [--log-format FORMAT]
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--cassette`, `-c` *(required)* | — | JSONL cassette path (must exist; exit 2 otherwise) |
| `--host`, `-h` | `127.0.0.1` | Bind address |
| `--port`, `-p` | `7878` | TCP port |
| `--upstream` | `https://api.openai.com` | Used only for echoed config; no requests sent |
| `--timing` | `realtime` | Streamed replay pacing: `realtime`, `fast`, `slow=<N>`, or a bare multiplier |
| `--log-format` | `text` | `text` or `json` |

### `--timing` values

| Value | Effect |
|---|---|
| `realtime` | Original wall-clock gaps between SSE chunks |
| `fast` | No sleeps; deliver chunks as fast as possible |
| `slow=<N>` | Multiply gaps by `N` (e.g. `slow=3` is 3x slower) |
| *bare float* | Equivalent multiplier (`1.0` = realtime, `0` = fast) |

### Examples

```bash
# Strict replay, no network
uv run reel replay -c tests/cassettes/quickstart.jsonl

# Skip sleeps in CI for speed
uv run reel replay -c c.jsonl --timing fast

# Simulate a slow network (3x)
uv run reel replay -c c.jsonl --timing slow=3
```

### Exit codes

| Code | When |
|---|---|
| `2` | Cassette file not found |

---

## `reel auto`

Replay if the cassette has a match for the request, otherwise forward upstream and capture. Default for local development loops.

### Synopsis

```bash
reel auto --cassette <path> [--host HOST] [--port PORT] [--upstream URL] [--timing MODE] [--log-format FORMAT]
```

### Options

Same as [`reel replay`](#reel-replay), except the cassette does not need to exist — it will be created on the first capture.

### Examples

```bash
# Default local dev loop
uv run reel auto -c tests/cassettes/quickstart.jsonl

# Auto mode against Anthropic (path-based routing picks the upstream)
uv run reel auto -c tests/cassettes/anthropic.jsonl
```

---

## `reel inspect`

Display a cassette's entries with filters. Default output is a Rich table; `-v` prints full bodies.

### Synopsis

```bash
reel inspect --cassette <path> [filters...] [--limit N] [--verbose]
```

### Options

| Option | Meaning |
|---|---|
| `--cassette`, `-c` *(required)* | Cassette JSONL to inspect |
| `--provider` | Exact provider: `openai`, `anthropic`, `gemini` |
| `--model` | Case-insensitive substring of the request body's `model` |
| `--status` | Response status: exact (`429`) or class (`2xx` / `4xx` / `5xx`) |
| `--has-tool-call` / `--no-tool-call` | Only entries that involve tools |
| `--regex` | Python regex applied to the JSON-serialized entry |
| `--limit`, `-n` | Stop after the first N matching entries |
| `--verbose`, `-v` | Print each entry's full body |

### Examples

```bash
# All entries, table view
uv run reel inspect -c tests/cassettes/quickstart.jsonl

# Only Anthropic 4xx responses
uv run reel inspect -c c.jsonl --provider anthropic --status 4xx

# First 3 GPT-5 calls with tool calls, full bodies
uv run reel inspect -c c.jsonl --model gpt-5 --has-tool-call -n 3 -v

# Find anything that looks like a leaked secret
uv run reel inspect -c c.jsonl --regex 'sk-[A-Za-z0-9]+'
```

---

## `reel cost`

Sum the token cost of every priced entry. Prices ship in a bundled table; override with `--pricing`.

### Synopsis

```bash
reel cost --cassette <path> [--pricing FILE] [--by GROUP]
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--cassette`, `-c` *(required)* | — | Cassette to price |
| `--pricing` | bundled | Override the bundled pricing table (JSON, USD per 1M tokens) |
| `--by` | `model` | Group rows by `provider`, `model`, or `total` |

### Examples

```bash
# Per-model cost breakdown
uv run reel cost -c tests/cassettes/quickstart.jsonl

# Aggregate by provider
uv run reel cost -c c.jsonl --by provider

# Single total
uv run reel cost -c c.jsonl --by total

# Use a custom pricing table
uv run reel cost -c c.jsonl --pricing my-prices.json
```

---

## `reel diff`

Compare two cassettes and report drift in models, responses, and cost.

### Synopsis

```bash
reel diff --left <path> --right <path> [--show-bodies / --no-show-bodies]
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--left`, `-l` *(required)* | — | The "before" cassette |
| `--right`, `-r` *(required)* | — | The "after" cassette |
| `--show-bodies` / `--no-show-bodies` | `show-bodies` | Show response-body snippets for entries whose bodies changed |

### Examples

```bash
# Compare a baseline cassette to a new run
uv run reel diff -l tests/cassettes/baseline.jsonl -r tests/cassettes/new.jsonl

# Hide bodies for a compact summary
uv run reel diff -l a.jsonl -r b.jsonl --no-show-bodies
```

---

## `reel stats`

Summarize a cassette: counts, error rate, tokens, TTFT distribution.

### Synopsis

```bash
reel stats --cassette <path> [--by GROUP]
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--cassette`, `-c` *(required)* | — | Cassette to summarize |
| `--by` | `summary` | Focus: `summary`, `provider`, or `status` |

### Examples

```bash
# Default summary
uv run reel stats -c tests/cassettes/quickstart.jsonl

# Per-provider breakdown
uv run reel stats -c c.jsonl --by provider

# Status-code distribution
uv run reel stats -c c.jsonl --by status
```

---

## `reel doctor`

Diagnose a Reel install: Python version, port availability, cassette path writability, upstream reachability, optional extras.

### Synopsis

```bash
reel doctor [--cassette <path>] [--skip-network]
```

### Options

| Option | Meaning |
|---|---|
| `--cassette`, `-c` | If set, check write permissions on the parent directory |
| `--skip-network` | Skip upstream reachability checks (useful in air-gapped envs) |

### Examples

```bash
# Full check
uv run reel doctor

# Air-gapped CI
uv run reel doctor --skip-network

# Verify a specific cassette path is writable
uv run reel doctor -c tests/cassettes/new.jsonl
```

---

## `reel redact`

Scrub secrets (and optionally PII) from an existing cassette. Capture-time redaction is on by default — `reel redact` is for post-hoc cleanup or applying new patterns to old cassettes.

### Synopsis

```bash
reel redact --cassette <path> [--keep-pii] [--output FILE] [--dry-run]
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--cassette`, `-c` *(required)* | — | Cassette to scrub |
| `--keep-pii` | off | Skip PII scrubbing (secrets are always scrubbed) |
| `--output`, `-o` | overwrite input | Write the redacted output to this path |
| `--dry-run` | off | Report what would change without writing |

### Examples

```bash
# Scrub in place
uv run reel redact -c tests/cassettes/old.jsonl

# Write to a new file
uv run reel redact -c old.jsonl -o clean.jsonl

# Preview without writing
uv run reel redact -c old.jsonl --dry-run

# Keep emails / phone numbers, scrub secrets only
uv run reel redact -c old.jsonl --keep-pii
```

### Exit codes

| Code | When |
|---|---|
| `2` | Cassette file not found |

---

## `reel version`

Print the installed Reel version and exit.

### Synopsis

```bash
reel version
```

### Example

```bash
$ uv run reel version
reel 0.0.1
```
