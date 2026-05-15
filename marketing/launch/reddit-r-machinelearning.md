# r/MachineLearning self-post

## Title

`[P] Reel — deterministic replay for OpenAI / Anthropic / Gemini APIs for reproducible LLM experiments`

(The `[P]` flair = Project. r/MachineLearning is strict about flairs.)

## Body

Reproducibility for LLM-driven experiments is awkward. The same prompt can produce different outputs across runs even at `temperature=0` due to server-side non-determinism, model deprecations, silent infra changes, and sampling differences across regions. If you're iterating on a prompt, evaluating an agent, or running ablations, you usually want the *exact* response bytes that came back the first time — not "something close."

Reel captures real OpenAI / Anthropic / Gemini HTTP exchanges into JSONL "cassettes" and replays them deterministically. It's a local HTTP proxy, not an SDK wrapper, so it sits below LangChain / LlamaIndex / dspy / instructor / your own client and captures the actual wire-level request and response — including SSE streams with their original TTFT and inter-chunk timing offsets preserved to within ~20ms.

### What this gives you

- **Frozen response set per experiment.** Every prompt/response pair lives in a JSONL file you can commit alongside the code that produced it. Re-running the experiment a month later, in a different region, or after a model deprecation produces the same outputs.
- **Cassette-level matcher config.** Default `normalized` mode is whitespace/key-order tolerant; `exact` for byte-for-byte; `ignore-fields` for stripping per-call IDs; `fuzzy` (embedding similarity, opt-in) for prompts that drift between iterations (e.g. a templated prompt where a timestamp leaks in).
- **Diff between runs.** `reel diff a.jsonl b.jsonl` reports what drifted between two cassettes — different models, different responses, different token counts, different cost.
- **Cost accounting per experiment.** `reel cost cassette.jsonl` sums tokens × current provider pricing tables, broken down by model. Useful when reporting "we spent $X on this evaluation suite."
- **Streaming preserved.** SSE chunks are captured with their wall-clock offsets and replayed via `asyncio.sleep(offset)`. Timing-sensitive code paths (UI streaming, token-level guardrails, early-stop logic) behave the same on replay as on the original call.

### Shape of a cassette entry

```jsonl
{"id":"req_...","ts":"2026-05-15T...","provider":"openai","mode":"chat.completions","request":{...},"response":{...},"stream_chunks":[{"delta":"Hi","t_offset_ms":42},{"delta":" there!","t_offset_ms":98}],"meta":{"matcher":"normalized","redacted":["api_key"]}}
```

Plain JSONL. One entry per call. Diffable in PRs.

### Architecture

```
your code ─► OpenAI/Anthropic/Gemini SDK ─► reel proxy :7878 ─► upstream API
                                                  │
                                                  ▼
                                          cassette JSONL
```

Three modes:

- `record` — always forward + capture
- `replay` — serve from cassette only; 404 on miss (no network, no API key)
- `auto` — replay if matched, else record (the default for local iteration)

Built on starlette + httpx. Adapters are thin per-provider modules that compute request fingerprints (model + messages + tools, normalized) and parse provider-specific SSE shapes. Adding a new provider is one file.

### Why this and not VCR.py / cassette libraries / mocks

- VCR.py works at the `urllib` / `requests` level and is brittle around streaming and per-SDK quirks. Reel works at HTTP, so it's SDK-agnostic and streaming-aware.
- Mocks drift. The bug you usually want to catch is in the *actual* bytes the provider sent back; a hand-written stub won't surface it.
- Reel never captures API keys (request headers are dropped by design). Secret + PII scrubbing runs at capture time, with a pre-commit hook that refuses any cassette still carrying a detectable secret.

### Status

Pre-alpha. Sprints 1-5 of 6 are in. 332 tests across analytics, multi-provider E2E, redaction, and the pytest plugin. CI matrix on Python 3.11 / 3.12 / 3.13. Apache 2.0. Web inspector UI + PyPI land in the current sprint.

Repo: <REPO_URL>
Docs: <DOCS_URL>

Honest critique welcome. Particularly interested in:

- where deterministic replay breaks down for the experiments you run (tool-call agent loops with branching is the one I'm least sure about)
- whether the `fuzzy` matcher is the right primitive for "prompt drifted slightly across iterations" or whether there's a cleaner abstraction
- which provider you'd want to see next (Bedrock / Vertex / Azure OpenAI / Mistral / Groq / Together are all on the post-MVP list)
