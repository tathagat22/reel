---
title: "pytest + LLM APIs — record/replay OpenAI, Anthropic, Gemini tests with Reel"
description: "Drop Reel's pytest plugin into an existing OpenAI / Anthropic / Gemini test suite to make it deterministic, free, and offline. A VCR.py / pytest-recording / pytest-httpx alternative that works at the HTTP layer."
---

# pytest

In this guide: drop Reel into an existing OpenAI / Anthropic / Gemini pytest
suite to make it deterministic, free, and offline — in under sixty seconds.

## 1. Install Reel

```bash
uv pip install reel-vcr    # or: pip install reel-vcr  (binary + import path stay `reel`)
```

The package ships a pytest plugin that auto-registers — no `conftest.py`
edits required.

## 2. Add the fixture to one test

```python
# tests/test_chat.py
from openai import OpenAI

def test_summarize(reel_cassette):
    client = OpenAI()  # picks up OPENAI_BASE_URL set by the fixture
    resp = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say hi"}],
    )
    assert resp.choices[0].message.content.strip()
```

That's it. The first time you run `pytest`, Reel forwards the call to
`api.openai.com` and captures it. Every subsequent run replays the cassette
with zero network calls — your test stays green even without an API key.

The cassette lands at `tests/cassettes/test_chat/test_summarize.jsonl`. It's
plain JSONL. Diff it in PRs. Grep it. Edit it.

## 3. Optional: use the decorator instead

If you'd rather keep cassette path/mode in the test signature:

```python
from reel.sdk import cassette

@cassette("tests/cassettes/summarize.jsonl", mode="auto")
def test_summarize():
    ...
```

The decorator and the fixture are interchangeable — pick whichever style
suits your suite.

## 4. Optional: tighten CI

Force replay mode in CI so a missing cassette becomes a loud failure
instead of a silent network call:

```bash
pytest --reel-mode replay
```

Now CI can run without API keys, and any test author who adds a new LLM
call has to commit the captured cassette alongside the test.

## 5. Markers for custom paths

```python
import pytest

@pytest.mark.cassette("tests/golden/summarize-v2.jsonl", mode="record")
def test_with_custom_path(reel_cassette):
    ...
```

Marker arguments:

| Arg / kwarg | Meaning |
|------|---------|
| `path` (positional or kwarg) | Cassette file location |
| `mode` (kwarg) | `"record"`, `"replay"`, or `"auto"` (default) |

## What's getting captured?

* The full request body (method, path, JSON payload)
* The full response (status, headers, body OR streaming chunks)
* Per-chunk timing for streamed responses (replay reproduces TTFT and gaps)
* **Not** the request headers — API keys live there and Reel never stores them

## What about secrets in the response?

Capture-time redaction is on by default. Common API-key shapes, Bearer
tokens, emails, and phone numbers are scrubbed before the cassette is
written. Disable PII scrubbing with `REEL_REDACT_PII=0`; secrets remain
scrubbed regardless.

## Cassette format

```json
{"schema_version":1,"id":"req_…","provider":"openai",
 "request":{"method":"POST","path":"/v1/chat/completions",
   "fingerprint":"sha256:…",
   "body":{"model":"gpt-5","messages":[…]}},
 "response":{"status":200,"headers":{…},
   "body":{"choices":[{"message":{"content":"hi"}}]}}}
```

One line per exchange. Append-only. Diff-friendly.

## See also

* `reel inspect <cassette>` — pretty-print a recorded session
* `reel diff <a> <b>` — diff two cassettes
* `reel redact -c <cassette>` — post-hoc scrub
* [Architecture overview](../architecture.md)
* [Roadmap](../roadmap.md)

## Next

- [Use replay mode in CI](ci.md)
- [Keep secrets out of cassettes](redaction.md)
