# r/LocalLLaMA self-post

## Title

`Reel — record real API calls once, replay them locally forever. No API keys in CI, no network round-trips, plain JSONL on disk.`

## Body

I built Reel because I was tired of two things: (1) needing a live OpenAI / Anthropic key sitting in CI secrets just to run tests, and (2) every test run pulling the same response from the same upstream over the public internet. It's wasteful and it's a key-rotation footgun.

Reel is a small local HTTP proxy that records real API calls into plain JSONL files and replays them locally without ever touching the network again. The whole point of the design is *local-first* — the cassette lives on your disk, in your repo, on your laptop. Once you've captured a call, your code can hit Reel forever and never need an upstream connection, never need a key, never leak a token to a CI runner.

### The "no API key in CI" bit

This is the part that matters most for self-hosted / local-LLM folks who treat cloud APIs as something you touch sparingly:

- Run `reel record` once locally, with your real key, to capture the exchanges you care about.
- Commit the JSONL cassette (keys + PII are scrubbed at capture time; a pre-commit hook refuses anything that still has a detectable secret in it).
- In CI: `pytest --reel-mode replay`. Any unmatched call 404s — the suite physically cannot reach the internet. No `OPENAI_API_KEY` in CI secrets. No `ANTHROPIC_API_KEY`. No surprise spend.
- The CI runner can be airgapped, offline, on a Raspberry Pi in a closet, whatever. It just reads JSONL off disk.

### Architecture is genuinely local

- Proxy is one Python process. starlette + httpx + uvicorn. No daemon, no service, no account.
- Cassettes are JSONL files in your repo. Not in a database, not in a vendor's cloud, not behind an account.
- No telemetry. No analytics. No "anonymous usage stats." Ever. (Hard rule in the project's `CLAUDE.md`.)
- Apache 2.0. Self-host the whole thing in your venv.

### Mixed local + cloud workflows

If you're running a local model for most paths and only hitting a cloud API for the hard cases (a pattern that's increasingly common), Reel cassettes the cloud calls so your test suite for the *whole* pipeline runs offline. You can swap your local model in and out, and the cloud responses stay frozen.

```bash
$ uv run reel auto --cassette tests/cassettes/eval.jsonl
$ export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
$ pytest tests/    # first run records, every run after replays
```

### What it does today

- OpenAI / Anthropic / Gemini HTTP APIs — record / replay / auto modes
- SSE streaming with TTFT and inter-chunk timing preserved (`--timing realtime | fast | slow=N`)
- Smart matcher modes: `exact`, `normalized` (default), `ignore-fields`, `fuzzy`
- Capture-time secret + PII redaction; pre-commit hook
- pytest plugin with `@cassette` decorator, fixture, and `--reel-mode` CLI flag
- Analytics CLI: `reel inspect / cost / diff / stats / doctor`
- Structured JSON logs, `jq`-pipeable
- 332 tests, strict ruff + pyright, CI on Python 3.11 / 3.12 / 3.13

### What it doesn't do (yet)

- No local-model adapter — but if your local model speaks an OpenAI-compatible API (llama.cpp server, vLLM, Ollama in OpenAI mode, LM Studio), pointing Reel's upstream at it works today via path-based routing.
- No Bedrock / Vertex / Azure OpenAI yet (post-MVP backlog).
- Pre-alpha — `git clone && uv sync` install for now; PyPI lands this sprint.

Repo: <REPO_URL>
Docs: <DOCS_URL>

Genuinely curious what r/LocalLLaMA thinks of the proxy-as-test-fixture model. Specifically: would a built-in local-model adapter (recording llama.cpp / Ollama / vLLM outputs into the same cassette format as the cloud ones) be useful, or is that overkill since you can already re-run the local model deterministically yourself?
