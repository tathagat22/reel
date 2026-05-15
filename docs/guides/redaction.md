---
title: "Keep API keys and PII out of Reel cassettes — redaction guide"
description: "How Reel scrubs API keys (OpenAI, Anthropic, Google, AWS, GitHub), Bearer tokens, emails, and phone numbers from cassettes at capture time. Includes the pre-commit hook that blocks unsafe commits."
---

# Redaction

In this guide: how Reel keeps secrets and PII out of cassettes, and how to scrub anything that slipped through.

## Three layers of defense

1. **Capture-time secret scrubbing** — every response body is run through a regex pass before the cassette line is written. Common key shapes are replaced with `[REDACTED]`.
2. **Capture-time PII scrubbing** — emails and phone numbers are also scrubbed by default. Opt out with `REEL_REDACT_PII=0`.
3. **Pre-commit hook** — refuses to stage any `*.jsonl` that contains a detectable secret pattern.

API keys live in request headers. Reel never stores request headers — they're dropped before serialization. There's nothing to scrub there because there's nothing to write.

## What gets scrubbed automatically

The default secret patterns cover:

- **OpenAI** keys (`sk-...`)
- **Anthropic** keys (`sk-ant-...`)
- **Google / Gemini** API keys (`AIza...`)
- **GitHub** tokens (`ghp_...`, `gho_...`, `ghs_...`)
- **AWS** access keys (`AKIA...`)
- **Slack** tokens (`xoxp-...`, `xoxb-...`)
- Bearer-style headers when echoed into bodies (`Authorization: Bearer ...`)

PII patterns (on by default, opt out with `REEL_REDACT_PII=0`):

- Email addresses
- Phone numbers (E.164 and common US/EU shapes)

Each match is replaced with `[REDACTED]`. The cassette stays valid JSONL and the request fingerprint is unaffected (fingerprints are computed before redaction is needed).

## Post-hoc scrub: `reel redact`

If a cassette was recorded before a new redaction pattern shipped, or you want to scrub PII from an old cassette, run:

```bash
uv run reel redact --cassette tests/cassettes/old.jsonl
```

By default this overwrites the input. Write to a new file with `--output`:

```bash
uv run reel redact -c tests/cassettes/old.jsonl -o tests/cassettes/clean.jsonl
```

Dry-run to see what would change without writing:

```bash
uv run reel redact -c tests/cassettes/old.jsonl --dry-run
```

Keep PII (e.g. for tests that need a real-looking email) but always scrub secrets:

```bash
uv run reel redact -c tests/cassettes/old.jsonl --keep-pii
```

## Pre-commit hook

Drop the repo-local hook in to refuse any staged cassette that contains a detectable secret:

```bash
uv run pre-commit install
```

The hook lives at `hooks/pre-commit-cassette-check.py`. It scans the staged content of every `*.jsonl` file and exits non-zero if a secret pattern matches. You can run it manually:

```bash
python hooks/pre-commit-cassette-check.py tests/cassettes/**/*.jsonl
```

Pair it with the [CI guide](ci.md) for a second pass on every PR.

## When redaction is wrong

If you're recording against a synthetic test API and want the raw bytes preserved (no scrubbing at all), set:

```bash
REEL_REDACT=0 uv run reel record --cassette tests/cassettes/raw.jsonl
```

This disables both secret and PII scrubbing. Be sure the upstream you're hitting never returns real credentials.

## Verifying

`reel inspect` shows you what's actually in a cassette:

```bash
uv run reel inspect -c tests/cassettes/quickstart.jsonl --regex 'sk-[A-Za-z0-9]'
```

If that command finds anything, your cassette is not safe to commit. Run `reel redact` and try again.

## Next

- [CI integration](ci.md)
- [CLI reference](../cli.md)
