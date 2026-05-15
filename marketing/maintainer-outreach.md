# Maintainer outreach — DM templates

These are scaffolds, not finished sends. Before each one: fill in the names, drop a one-liner about something the maintainer shipped this month, and re-read for tone — if it sounds like a templated cold-outreach blast, rewrite it. The DMs that work are short, specific, and lead with "here is the thing for your users," not "please look at my project."

Every template is ~3 sentences. One direct ask per message. No follow-ups for 7 days minimum.

---

## 1. LangChain — Harrison Chase (and team)

> Hi {NAME} — quick one. I built Reel, an HTTP-proxy-level "VCR for LLM APIs" that records OpenAI / Anthropic / Gemini calls (including streaming) into plain JSONL cassettes and replays them deterministically, so LangChain test suites can run in CI with zero spend and no API keys. The integration is one line: `OPENAI_BASE_URL=http://127.0.0.1:7878/v1` in the test fixture, no LangChain-specific code path required. Would you take a look and tell me if a one-paragraph mention in the LangChain testing docs would be welcome — happy to write it?
>
> Repo: <REPO_URL>

---

## 2. LlamaIndex — Jerry Liu (and team)

> Hi {NAME} — Reel is a local HTTP proxy that records LLM API calls into JSONL cassettes and replays them deterministically, so LlamaIndex test suites can run offline with no API key and no spend; it sits below the SDK, so it works with any LLM your users plug in. The pytest plugin is one decorator: `@cassette("path/to/file.jsonl")`. Would a short example in the LlamaIndex testing guide be useful — and if so, would you prefer I open a PR or send a draft for review first?
>
> Repo: <REPO_URL>

---

## 3. dspy — Omar Khattab (and team)

> Hi {NAME} — Reel records OpenAI / Anthropic / Gemini calls into plain JSONL cassettes and replays them deterministically, including streaming with original TTFT preserved. The fit with dspy is unusually clean: prompt-iteration loops and evaluations stay reproducible across runs, and `reel diff a.jsonl b.jsonl` shows exactly what drifted between two compilation runs. Would you take a look and tell me if a one-paragraph note in the dspy reproducibility / evals docs would be welcome?
>
> Repo: <REPO_URL>

---

## 4. instructor — Jason Liu

> Hi Jason — Reel is a local proxy that records OpenAI / Anthropic / Gemini calls into JSONL cassettes and replays them in tests, so instructor users can test their schema-extraction prompts in CI without spending real money or stashing keys. Tools and structured outputs round-trip correctly. Would a `tests/test_with_reel.py` example in the instructor cookbook be welcome — I'd send a PR if so?
>
> Repo: <REPO_URL>

---

## 5. Vercel AI SDK — Vercel team

> Hi {NAME} — Reel is an HTTP-proxy-style "VCR for LLM APIs" — record once, replay deterministically, including streaming. The current pytest plugin is Python-only; a vitest plugin for the Vercel AI SDK is on the post-MVP backlog, and I'd love a maintainer's perspective on whether a one-line `process.env.OPENAI_BASE_URL = "http://127.0.0.1:7878/v1"` in a vitest setup file would be the right integration point. Would you take 60 seconds and tell me if that's where you'd want this to slot in?
>
> Repo: <REPO_URL>

---

## 6. OpenAI Python SDK — staff awareness only

> Hi {NAME} — sending this for awareness, not asking for an integration. I've shipped Reel, an open-source local HTTP proxy that records `openai-python` calls into JSONL cassettes and replays them deterministically; the SDK works with it via the standard `OPENAI_BASE_URL` env var with zero changes. Flagging in case you ever get questions from users about deterministic testing — happy to answer anything off-list.
>
> Repo: <REPO_URL>

---

## 7. Anthropic SDK — staff awareness only

> Hi {NAME} — same note as above, for the Anthropic SDK side. Reel records `anthropic-python` calls (including streaming via the `messages.stream(...)` shape) into JSONL cassettes and replays them deterministically; users plug it in by setting the SDK's `base_url` to `http://127.0.0.1:7878`. Flagging for awareness only — no integration request — but happy to answer questions if any come up from your side.
>
> Repo: <REPO_URL>

---

## Sending notes

- Personalize the first line of every DM with something concrete the recipient shipped in the last 30 days. Generic "love your work" openers get deleted.
- Lead with **what their users get**, not what Reel is. If you can't articulate the win for *their* audience in one sentence, don't send the DM.
- One ask per message. The asks above are deliberately small (a paragraph in docs, a look at an example, a confirmation that an integration point is right). Big asks ("merge this PR") come *after* the first reply.
- Don't follow up for at least 7 days. If they ignore the second message, drop it — they're busy, not rude.
- Keep a tracking row in `outreach.csv` (`name, sent_date, response, status`) so you don't double-send.
