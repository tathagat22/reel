---
title: "OpenAI + Anthropic + Gemini on one Reel proxy — multi-provider setup"
description: "Run OpenAI, Anthropic, and Gemini through a single Reel proxy port. Path-based auto-routing or explicit /openai, /anthropic, /gemini URL prefixes. One cassette can hold multiple providers."
---

# Multi-provider

In this guide: run OpenAI, Anthropic, and Gemini through a single Reel proxy at the same time.

## The two routing styles

Reel decides which upstream to forward to based on the request URL path. There are two ways to do it:

1. **Path-based auto-routing** — Reel inspects the path and infers the provider from its shape (`/v1/chat/completions` -> OpenAI, `/v1/messages` -> Anthropic, `/v1beta/models/.../generateContent` -> Gemini).
2. **Explicit `/<provider>/...` URL prefix** — unambiguous, useful when the same path exists in multiple providers or when you want to be explicit in tests.

Both work against the same cassette. The captured `provider` field records which upstream each call went to, so replay is never ambiguous.

## One proxy, three SDKs

Start the proxy once:

```bash
uv run reel auto --cassette tests/cassettes/multi.jsonl
```

Then point each SDK at the same `http://127.0.0.1:7878` and let path-based routing handle the rest:

=== "OpenAI"

    ```python
    from openai import OpenAI

    client = OpenAI(base_url="http://127.0.0.1:7878/v1")
    resp = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say hi"}],
    )
    ```

=== "Anthropic"

    ```python
    from anthropic import Anthropic

    client = Anthropic(base_url="http://127.0.0.1:7878")
    resp = client.messages.create(
        model="claude-opus-4",
        max_tokens=128,
        messages=[{"role": "user", "content": "Say hi"}],
    )
    ```

=== "Gemini"

    ```python
    import google.generativeai as genai

    genai.configure(
        api_key="...",
        transport="rest",
        client_options={"api_endpoint": "http://127.0.0.1:7878"},
    )
    model = genai.GenerativeModel("gemini-2.0-flash")
    resp = model.generate_content("Say hi")
    ```

All three calls land in the same JSONL cassette. Each entry's `provider` field tells you who it spoke to.

## Explicit provider prefix

When path-based routing can't disambiguate (or when you want to make the routing decision explicit), prefix the path with `/<provider>`:

```
http://127.0.0.1:7878/openai/v1/chat/completions
http://127.0.0.1:7878/anthropic/v1/messages
http://127.0.0.1:7878/gemini/v1beta/models/gemini-2.0-flash:generateContent
```

The prefix is stripped before forwarding upstream. Cassettes still record the canonical provider path.

## Different upstreams per provider

The default `--upstream` only configures the OpenAI fallback. Anthropic and Gemini route to their public APIs unconditionally. If you front any provider with a custom gateway, set the provider-specific environment variables before starting the proxy:

```bash
export REEL_OPENAI_UPSTREAM=https://my-openai-gateway.example.com
export REEL_ANTHROPIC_UPSTREAM=https://my-anthropic-gateway.example.com
export REEL_GEMINI_UPSTREAM=https://my-gemini-gateway.example.com

uv run reel auto --cassette tests/cassettes/multi.jsonl
```

## Matching is provider-aware

Each provider's adapter normalizes requests before fingerprinting (OpenAI keys are sorted, Anthropic `system` is folded into messages, Gemini `contents` is canonicalized). Two semantically-equal requests across whitespace and key-order differences still match.

See [Architecture](../architecture.md) for the per-provider matching details.

## Next

- [Keep secrets out of cassettes](redaction.md)
- [CLI reference](../cli.md)
