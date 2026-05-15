# Roadmap

Reel is built and shipped in well-scoped milestones. Everything below has been delivered.

## Shipped — v0.1.0

| Milestone | What landed |
|---|---|
| Foundation | Repo, license, CI matrix on Python 3.11 / 3.12 / 3.13, project scaffolding |
| Core proxy | OpenAI adapter, `record` / `replay` / `auto` modes, JSONL cassette format |
| Streaming | SSE capture with millisecond timing fidelity, `--timing realtime / fast / slow=N` |
| Multi-provider | Anthropic + Gemini adapters, path-based and explicit prefix routing |
| Smart matching | `exact` / `normalized` / `ignore-fields` / `fuzzy` (optional sentence-transformers) |
| Redaction | Capture-time secret + PII scrubbing, post-hoc `reel redact`, pre-commit hook |
| pytest plugin | Auto-registered via `pytest11`, `reel_cassette` fixture, `@cassette` decorator, `--reel-mode` |
| Analytics CLI | `reel inspect / cost / diff / stats / doctor` over cassette JSONL |
| Observability | Structured per-request JSON logs (`--log-format json`) |
| Web inspector | `reel ui` — local HTMX cassette browser |
| Distribution | PyPI publish via Trusted Publishing, docs site on GitHub Pages, Homebrew formula scaffold |

See the [architecture overview](architecture.md) for how the pieces fit together.

## What's next (not yet committed to a release)

These are tracked as ideas; comment on a GitHub issue if you'd use any of them and want to push them up the queue.

- **Zero-config onboarding** — `reel up` / `reel down` / `eval "$(reel env)"` so users never set env vars by hand.
- **`reel run -- <cmd>`** — wrapper that auto-spawns the proxy for one subprocess and tears it down on exit.
- **Embedding-cache mode** — transparent dedupe of `/v1/embeddings` calls (model-keyed, cross-session). Pure win, zero risk.
- **MCP server** — exposes `lookup_cassette` / `report_savings` / `embed_cached` as tools that agents can wire in deliberately.
- **TypeScript SDK + vitest plugin**
- **Auto-instrumentation packages for LangChain / LlamaIndex / AI SDK**
- **Tool-call multi-turn matching for agent loops**
- **Snapshot mode** — assert response shape rather than exact content
- **More provider adapters**: Bedrock, Vertex, Azure OpenAI, Mistral, Groq, Cerebras, Together
- **Reel Cloud (eventually)** — team cassette sharing + dashboards, only if there's demand

## Contributing

PRs welcome. See [`CONTRIBUTING.md`](https://github.com/tathagat22/reel/blob/main/CONTRIBUTING.md).
