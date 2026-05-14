# Demo assets

Manual screen recordings live here. Sprint 2.9 placeholder — needs a real
`streaming.gif` showing a pytest run go from "$X cost per run" to "$0".

Suggested capture flow:

1. Run a pytest test against a real OpenAI streaming chat completion; show the
   API spend.
2. Wrap with Reel auto mode: `uv run reel auto -c tests/cassettes/demo.jsonl`.
3. Re-run the test; show zero network traffic and the same streamed output.
4. Highlight the cassette in JSONL form for diff-review appeal.

Recording tips:
- Use [`asciinema`](https://asciinema.org/) for terminal-only flows.
- Use [Tella](https://tella.tv/) / Loom for a polished side-by-side.
- Keep the GIF under 5 MB so GitHub doesn't degrade it.

Once `streaming.gif` lives here, wire it into the README hero section.
