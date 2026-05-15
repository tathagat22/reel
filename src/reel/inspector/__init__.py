"""Reel web inspector — local HTMX UI for browsing JSONL cassettes.

A small Starlette app, served by ``reel ui`` on a port separate from the
proxy (default ``:7879``). Mirrors the filter semantics of ``reel inspect``
in a browser: provider / model / status / has-tool-call / regex / limit.
No SPA, no JS framework, no auth — strictly a single-user debug tool.

Public entry points:

* :func:`reel.inspector.server.create_app` — build the ASGI app.
* :func:`reel.inspector.server.serve` — run it under uvicorn.
"""
