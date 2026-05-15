# Getting started

In this guide: install Reel, record your first cassette, and replay it without touching the network — in under five minutes.

## 1. Install

From PyPI:

```bash
pip install reel-vcr            # CLI binary, import path, and GitHub repo all stay `reel`
reel --help
```

Or from source if you want the latest unreleased commits:

```bash
git clone https://github.com/tathagat22/reel
cd reel && uv sync
uv run reel --help
```

## 2. Start the proxy in `auto` mode

`auto` replays if a matching call is on the cassette, otherwise it forwards to the upstream and captures the response. It's the right default for local development.

```bash
uv run reel auto --cassette tests/cassettes/quickstart.jsonl
```

You'll see:

```
reel 0.0.1 · mode=auto
  listen   http://127.0.0.1:7878
  upstream https://api.openai.com
  cassette tests/cassettes/quickstart.jsonl
```

## 3. Point your SDK at the proxy

```bash
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
export OPENAI_API_KEY=sk-...   # real key — Reel forwards it on the first run only
```

## 4. Run your code

```python
from openai import OpenAI

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": "Say hi"}],
)
print(resp.choices[0].message.content)
```

First run: Reel proxies to `api.openai.com` and writes the exchange to the cassette.

```bash
$ cat tests/cassettes/quickstart.jsonl
{"id":"req_...","provider":"openai","request":{...},"response":{...}}
```

Run it again. Reel sees the matching request and serves the cached response. No network call. No API spend.

## 5. Lock CI to replay-only

Once a cassette is committed, force replay so missing entries become loud failures rather than silent network calls:

```bash
uv run reel replay --cassette tests/cassettes/quickstart.jsonl
```

A cache miss in `replay` returns HTTP 404 — no upstream call.

## What was captured?

- The full request body (method, path, JSON payload)
- The full response (status, headers, body, or streamed chunks with per-chunk timing)
- **Not** request headers — API keys live there and Reel never stores them
- Secrets and PII in response bodies are scrubbed before the cassette is written ([details](guides/redaction.md))

## Next

- [Add Reel to your pytest suite](guides/pytest.md)
- [Use replay mode in CI](guides/ci.md)
- [Run OpenAI, Anthropic, and Gemini through one proxy](guides/multi-provider.md)
- [Full CLI reference](cli.md)
