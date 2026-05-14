# Example — OpenAI SDK + Reel

A 30-line pytest demonstrating Reel proxying real OpenAI SDK calls through
either the `@cassette` decorator or the `reel_cassette` fixture.

## Run

```bash
# From repo root
uv run pytest examples/openai-sdk -v
```

First run uses a mocked upstream (via `respx`) — no API key required.
A real run against `api.openai.com` would record on first invocation and
replay on every subsequent one.

## What to look at

* `test_chat.py` — fixture and decorator forms side by side
* The cassette appears at `examples/openai-sdk/cassettes/test_chat/` after
  the first run. Open it — it's plain JSONL.
