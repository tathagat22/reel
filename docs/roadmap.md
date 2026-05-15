# Roadmap

Reel is built sprint by sprint. The canonical, always-up-to-date plan lives in [`docs/SPRINT_SHEET.md`](https://github.com/tathagat22/reel/blob/main/docs/SPRINT_SHEET.md) in the repo. The summary below stays in sync sprint-by-sprint.

## Shipped (Sprints 0-5)

| Sprint | What landed |
|---|---|
| 0 | Repo, license, CI, project scaffolding |
| 1 | Core proxy, OpenAI adapter, `record` / `replay` / `auto`, cassette JSONL format |
| 2 | SSE streaming with millisecond timing fidelity, `--timing` modes |
| 3 | Anthropic + Gemini adapters, smart matcher (`exact` / `normalized` / `ignore-fields` / `fuzzy`), secret + PII redaction, pre-commit hook |
| 4 | pytest plugin (auto-registered), `@cassette` decorator, `--reel-mode` CLI flag, example projects |
| 5 | Analytics CLI: `reel inspect / cost / diff / stats / doctor`, structured JSON per-request logs |

See the [architecture overview](architecture.md) for how the pieces fit together.

## In flight (Sprint 6)

| ID | Task |
|---|---|
| 6.1-6.3 | Web inspector UI (HTMX, no SPA) |
| 6.4 | Docs site (this site) |
| 6.5 | Landing page polish |
| 6.6 | 60-second demo video |
| 6.7-6.9 | Launch posts, newsletter outreach, maintainer outreach |
| 6.10 | PyPI + Homebrew formula |

## Post-MVP backlog

- TypeScript SDK + vitest plugin
- Tool-call multi-turn matching for agent loops
- Auto-instrumentation packages for LangChain / LlamaIndex / AI SDK
- Mutation testing on captured prompts
- Snapshot mode (assert shape, not content)
- More provider adapters: Bedrock, Vertex, Azure OpenAI, Mistral, Groq, Cerebras, Together
- Optional hosted dashboard for team cassette sharing (Reel Cloud)

## Contributing

PRs welcome. See [`CONTRIBUTING.md`](https://github.com/tathagat22/reel/blob/main/CONTRIBUTING.md). The sprint sheet is the source of truth for what's in flight — pick the lowest open ID in the current sprint.
