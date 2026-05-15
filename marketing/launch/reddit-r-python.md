# r/Python self-post

## Title

`Reel — a VCR-style proxy for OpenAI / Anthropic / Gemini that turns flaky LLM tests into deterministic ones`

## Body

I wrote a small tool that I think solves a problem a lot of Python folks doing LLM work have hit: tests that hit real OpenAI / Anthropic / Gemini APIs are slow, non-deterministic, and quietly expensive. Mocks help, but they drift — and the bugs I actually want to catch live in the bytes on the wire, not in whatever stub I wrote three months ago.

Reel is a local HTTP proxy. You start it on `:7878`, point your SDK's base URL at it, and the first call gets forwarded upstream and captured into a plain JSONL "cassette." Every call after that is served from the cassette — including SSE streams, with the original TTFT and inter-chunk timing preserved. The proxy approach means it works with any SDK or framework that speaks HTTP — `openai`, `anthropic`, `google-generativeai`, plus everything built on top: LangChain, LlamaIndex, dspy, instructor, your own client.

Quick demo:

```
$ uv run reel auto --cassette tests/cassettes/quickstart.jsonl
reel 0.0.1 · mode=auto
  listen   http://127.0.0.1:7878
  upstream https://api.openai.com
  cassette tests/cassettes/quickstart.jsonl

$ export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
$ export OPENAI_API_KEY=sk-...
$ python -c "
from openai import OpenAI
c = OpenAI()
print(c.chat.completions.create(
    model='gpt-5',
    messages=[{'role':'user','content':'Say hi'}],
).choices[0].message.content)
"
Hi there!

$ cat tests/cassettes/quickstart.jsonl
{"id":"req_...","ts":"2026-05-15T...","provider":"openai", ...}

# Unplug the network. Run the same Python again. Same answer. Zero cost.
```

The pytest plugin is the part most r/Python folks will care about. It auto-registers via the `pytest11` entry point, so once `reel` is installed in your venv you can use:

```python
import pytest
from reel import cassette

@cassette("tests/cassettes/test_chat.jsonl")
def test_chat():
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say hi"}],
    )
    assert "hi" in resp.choices[0].message.content.lower()
```

In CI: `pytest --reel-mode replay`. Any unmatched request 404s, so the suite physically cannot reach the internet and cannot accidentally spend money. No API key required in CI. Cassettes get refreshed on purpose, locally, when you want to.

Project layout:

```
src/reel/
├── proxy/      # starlette + httpx HTTP/SSE proxy core
├── adapters/   # openai.py · anthropic.py · gemini.py
├── cassette/   # schema, writer, reader, matcher, codec, store
├── redact/     # secret + PII scrubbing at capture time
├── cli/        # reel record | replay | auto | inspect | cost | diff | ...
└── sdk/        # @cassette decorator + pytest plugin
```

A few things I think are worth highlighting:

- **Cassettes are plain JSONL.** One JSON object per request. You diff them in PRs to see what changed in your prompts. `grep`, `jq`, the usual.
- **Secrets are scrubbed at capture time** for OpenAI / Anthropic / Google / GitHub / AWS / Slack key shapes and Bearer tokens. PII (email + phone) too — opt out with `REEL_REDACT_PII=0`. There's a pre-commit hook (`hooks/pre-commit-cassette-check.py`) that refuses any staged JSONL still carrying a detectable secret.
- **Matcher modes** for prompts that drift slightly: `exact`, `normalized` (default — whitespace and key-order tolerant), `ignore-fields` (drop per-call `request_id` / `trace_id`), and `fuzzy` (embedding similarity, optional `reel[fuzzy]` install). Per-cassette config via an optional `_meta` line so you pick the mode once.
- **Analytics CLI** for the cassettes you already have: `reel inspect / cost / diff / stats / doctor`. Cost uses current pricing tables for the big three providers, `diff` shows what regressed between two cassettes, `stats` gives you TTFT distributions for streaming entries.
- **Logs are structured JSON** (`--log-format json`) so they pipe straight to `jq`. No telemetry, no analytics, no "anonymous usage stats."

Stack: starlette + uvicorn + httpx + pydantic v2 + typer + rich. `uv` for package management. Strict ruff + pyright. 332 tests across analytics, multi-provider E2E, redaction, and the pytest plugin. CI matrix on Python 3.11 / 3.12 / 3.13. Apache 2.0.

Pre-alpha — sprints 1-5 of 6 are in. Web inspector UI + PyPI + Homebrew land in the current sprint. For now it's a `git clone && uv sync` install.

Repo: <REPO_URL>
Docs: <DOCS_URL>

Feedback wanted. Particularly interested in:

- whether the matcher modes cover the cases you actually hit (or where they fall short)
- the pytest plugin's ergonomics — decorator vs. fixture vs. marker — which would you reach for
- any LLM-test pain that this *doesn't* address
