# CI

In this guide: run your LLM-touching tests on every push without an API key and without hitting the network.

## The core idea

Once a cassette exists in your repo, CI should refuse to make real API calls. `pytest --reel-mode replay` enforces that: a missing entry becomes a loud test failure instead of a silent (and billable) upstream call.

```bash
pytest --reel-mode replay
```

You commit cassettes alongside the tests that produced them. CI never needs an API key.

## GitHub Actions

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run tests (replay only — no network)
        run: uv run pytest --reel-mode replay
```

No `OPENAI_API_KEY`, no `ANTHROPIC_API_KEY`. The proxy serves every recorded call from disk.

## GitLab CI

```yaml
# .gitlab-ci.yml
test:
  image: python:3.12
  before_script:
    - pip install uv
    - uv sync --frozen
  script:
    - uv run pytest --reel-mode replay
```

## CircleCI

```yaml
# .circleci/config.yml
version: 2.1
jobs:
  test:
    docker:
      - image: cimg/python:3.12
    steps:
      - checkout
      - run: pip install uv && uv sync --frozen
      - run: uv run pytest --reel-mode replay

workflows:
  test:
    jobs:
      - test
```

## Cassettes in git

Commit cassettes the same way you commit fixtures:

```
tests/
├── cassettes/
│   ├── test_chat/
│   │   ├── test_summarize.jsonl
│   │   └── test_translate.jsonl
│   └── test_tools/
│       └── test_function_calling.jsonl
└── test_chat.py
```

The repo-local pre-commit hook (`hooks/pre-commit-cassette-check.py`) refuses any `*.jsonl` containing a detectable secret pattern. Enable it once:

```bash
uv run pre-commit install
```

See [Redaction](redaction.md) for what gets scrubbed and how.

## When a cassette miss is correct behaviour

You changed a prompt. The captured request no longer matches what your code now sends. The replay misses and the test fails — exactly right. Re-record:

```bash
# Locally, with a key in the environment:
uv run pytest --reel-mode record   # forwards + re-captures
```

Then commit the updated cassette. CI replays the new bytes.

## Tightening further

- **Run `make check` in CI** — lint + types + tests, all replay-only.
- **Scan cassettes for secrets** as a separate CI step using the same hook script:
  ```bash
  python hooks/pre-commit-cassette-check.py tests/cassettes/**/*.jsonl
  ```
- **Pin upstream URLs** with `--upstream` if you front the API with a custom gateway.

## Next

- [Run OpenAI, Anthropic, and Gemini through one proxy](multi-provider.md)
- [Redaction details](redaction.md)
