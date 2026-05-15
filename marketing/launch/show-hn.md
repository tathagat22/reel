# Show HN: Reel – VCR for LLM APIs (record once, replay forever)

## Title

`Show HN: Reel – VCR for LLM APIs (record once, replay forever)`

(79 chars — fits HN's 80-char title limit.)

## Body

LLM tests are slow, flaky, and quietly expensive. After a colleague complained that CI was billing real OpenAI dollars on every PR and that one prompt regression took a week to bisect, I wrote Reel.

Reel is a tiny local HTTP proxy. Point your OpenAI / Anthropic / Gemini SDK at `http://127.0.0.1:7878` and the first call gets forwarded upstream and captured into a plain-text JSONL "cassette." Every call after that is served from disk — including SSE streams, with the original TTFT and inter-chunk gaps preserved within ~20ms. No SDK lock-in, no mocks, no real network in CI, no surprise spend.

The technical choice that makes it different: it's an HTTP proxy, not a Python monkey-patch. So it works with any SDK, any language, any framework — LangChain, LlamaIndex, dspy, instructor, your homegrown wrapper, doesn't matter. Cassettes are JSONL: you `grep` them, `jq` them, `git diff` them in PRs, and a pre-commit hook refuses to commit any file that still has a secret in it (keys are scrubbed at capture time by default; PII too).

The 30-second demo:

```bash
# Terminal 1
uv run reel auto --cassette tests/cassettes/quickstart.jsonl

# Terminal 2
export OPENAI_BASE_URL=http://127.0.0.1:7878/v1
export OPENAI_API_KEY=sk-...    # only needed for the first run
python -c "
from openai import OpenAI
c = OpenAI()
r = c.chat.completions.create(
    model='gpt-5',
    messages=[{'role':'user','content':'Say hi'}],
)
print(r.choices[0].message.content)
"
# Run it again with the network unplugged — same response, zero cost.
```

There's also a pytest plugin (`@cassette(...)` decorator, `pytest --reel-mode replay` for CI), a smart matcher with `exact / normalized / ignore-fields / fuzzy` modes for prompts that drift slightly between runs, and an analytics CLI: `reel inspect / cost / diff / stats / doctor` for browsing cassettes, summing token cost against current pricing tables, and diffing two cassettes to see what regressed.

Pre-alpha — sprints 1-5 of 6 are in. 332 tests. Apache 2.0. Repo: <REPO_URL>. Docs: <DOCS_URL>.

I'm the author, happy to answer questions — particularly interested in how people currently handle LLM-test reproducibility and whether the matcher modes cover the cases you hit in practice.
