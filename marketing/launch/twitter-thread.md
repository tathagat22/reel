# Twitter / X thread

Each tweet below is under 280 characters. The first tweet is the hook; everything after is the walkthrough. Numbering uses `1/`, not `1/10`.

---

**1/**

Your LLM tests cost real money and they're flaky.

Reel records OpenAI / Anthropic / Gemini calls once, replays them forever — including streaming, with the original TTFT preserved.

Free CI. Deterministic. No SDK lock-in.

<REPO_URL>

---

**2/**

The pain: one of my favorite test suites takes 90 seconds and bills $0.40 per CI run. Multiply by every PR push. A prompt regression once took a week to bisect because I couldn't reproduce the failing call locally.

Mocks don't help — the bug *was* in the bytes on the wire.

---

**3/**

Reel is an HTTP proxy on `:7878`. Point your SDK at it:

```
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
```

First run: it forwards upstream and writes a JSONL cassette. Every run after: it replays from disk. Network unplugged, same response, zero cost.

---

**4/**

Cassettes are plain JSONL — one entry per call. Diff them in PRs to see exactly what changed in your prompts. Grep them. `jq` them. Redact them.

A pre-commit hook refuses to commit any cassette still carrying a detectable secret. Keys + PII are scrubbed at capture time.

---

**5/**

Pytest plugin ships in the box:

```python
from reel import cassette

@cassette("tests/cassettes/chat.jsonl")
def test_chat():
    resp = openai.chat.completions.create(...)
    assert "hi" in resp.choices[0].message.content
```

Or `pytest --reel-mode replay` in CI. No API key required.

---

**6/**

CI mode is the killer feature. Set `--reel-mode replay` and any unmatched request 404s — your test suite cannot accidentally hit a real API, cannot leak a key, cannot bill you. You decide when cassettes get refreshed.

A junior on the team can run the suite the day they join.

---

**7/**

Analytics CLI for cassettes you already have:

- `reel inspect` — pretty-print + filters
- `reel cost` — tokens × current OpenAI/Anthropic/Gemini pricing
- `reel diff a b` — what drifted between two runs
- `reel stats` — TTFT distribution, errors, tokens

---

**8/**

Architecture:

```
SDK ─► reel :7878 ─► upstream
            │
            ├ auto:   replay-or-record
            ├ record: forward + capture
            └ replay: cassette only
```

No monkey-patching. Any SDK, any language.

---

**9/**

Built on starlette + httpx + pydantic v2. Strict ruff + pyright. 332 tests across analytics, multi-provider E2E, redaction, and the pytest plugin. CI on Python 3.11 / 3.12 / 3.13.

Pre-alpha. Apache 2.0. PyPI lands this sprint.

---

**10/**

Repo: <REPO_URL>
Docs: <DOCS_URL>

Would love feedback — especially from anyone with a flaky LLM test suite or a CI bill they wish would go away. What does your current setup look like?
