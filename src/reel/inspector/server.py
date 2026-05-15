"""Reel web inspector — Starlette + HTMX server.

A second small ASGI app, **separate from the proxy**, that lets a developer
browse a JSONL cassette in a browser. Same filter semantics as
``reel inspect`` (provider / model / status / has-tool-call / regex / limit)
expressed as query-string params on ``GET /entries``.

The cassette is loaded once into memory at lifespan startup via
:class:`reel.cassette.store.Cassette`; subsequent requests filter that
in-memory list — there's no per-request file I/O. Filtering reuses
:func:`reel.analytics.filters.apply` so the inspect CLI and the inspector
share a single source of truth.

Templates: Jinja2 with ``{% extends %}`` inheritance. The ``index.html``
view pre-renders the initial row table on the server using the same
fragment HTMX swaps into (``_rows.html``), so the page is fully usable
with JavaScript disabled.
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import uvicorn
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from reel.analytics.filters import FilterSpec, apply
from reel.cassette.schema import CassetteEntry
from reel.cassette.store import Cassette

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7879

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


# ─── Jinja environment ─────────────────────────────────────────────────


def _build_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
        enable_async=False,
    )
    env.filters["pretty_json"] = _pretty_json
    env.filters["status_class"] = _status_class
    env.filters["short_ts"] = _short_ts
    env.filters["truncate_str"] = _truncate
    return env


# ─── Filter parsing (query string → FilterSpec) ────────────────────────


def _parse_optional_bool(raw: str | None) -> bool | None:
    """Empty/missing → ``None``; ``true``/``1``/``yes`` → ``True``; anything else → ``False``."""
    if raw is None:
        return None
    v = raw.strip().lower()
    if v == "":
        return None
    return v in ("true", "1", "yes", "on")


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_optional_str(raw: str | None) -> str | None:
    if raw is None:
        return None
    v = raw.strip()
    return v or None


def _build_filter_spec(query: dict[str, str]) -> FilterSpec:
    """Translate a query-string dict into a :class:`FilterSpec`.

    Mirrors the flags accepted by ``reel inspect`` so the two surfaces stay
    in lock-step — empty/blank fields are treated as ``None`` so the form
    can submit unset filters without filtering them out.
    """
    regex_raw = _parse_optional_str(query.get("regex"))
    pattern: re.Pattern[str] | None = None
    if regex_raw is not None:
        try:
            pattern = re.compile(regex_raw)
        except re.error:
            pattern = None
    return FilterSpec(
        provider=_parse_optional_str(query.get("provider")),
        model=_parse_optional_str(query.get("model")),
        status=_parse_optional_str(query.get("status")),
        has_tool_call=_parse_optional_bool(query.get("has_tool_call")),
        regex=pattern,
        limit=_parse_optional_int(query.get("limit")),
    )


# ─── Row-projection helpers (entry → template-friendly dict) ───────────


def _iter_filtered_rows(entries: list[CassetteEntry], spec: FilterSpec) -> Iterator[dict[str, Any]]:
    """Yield row dicts for every entry that matches ``spec``.

    Cassette-wide indices (not post-filter positions) are emitted so detail
    links remain stable regardless of which filters are active. Single-pass:
    we look up each filtered entry's index via an identity map so we don't
    re-scan the list per match.
    """
    idx_by_id: dict[int, int] = {id(e): i for i, e in enumerate(entries)}
    for entry in apply(spec, entries):
        yield _row_dict(idx_by_id[id(entry)], entry)


def _row_dict(idx: int, entry: CassetteEntry) -> dict[str, Any]:
    """Project a :class:`CassetteEntry` into the fields the row template needs."""
    return {
        "idx": idx,
        "ts": entry.ts,
        "short_ts": _short_ts(entry.ts),
        "provider": entry.provider,
        "method": entry.request.method,
        "path": entry.request.path,
        "model": _model_name(entry) or "-",
        "status": entry.response.status,
        "status_class": _status_class(entry.response.status),
        "tokens": _tokens_summary(entry),
        "summary": _body_summary(entry),
    }


def _model_name(entry: CassetteEntry) -> str | None:
    body = entry.request.body
    if isinstance(body, dict):
        model = cast(dict[str, Any], body).get("model")
        if isinstance(model, str):
            return model
    return None


def _short_ts(ts: str) -> str:
    """Trim ISO timestamps to ``HH:MM:SS`` to keep table rows narrow."""
    return ts.split("T", 1)[1].split("+", 1)[0] if "T" in ts else ts


def _status_class(code: int) -> str:
    if 200 <= code < 300:
        return "green"
    if 300 <= code < 400:
        return "yellow"
    return "red"


def _truncate(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _tokens_summary(entry: CassetteEntry) -> str:
    body = entry.response.body
    if not isinstance(body, dict):
        return "-"
    d = cast(dict[str, Any], body)
    usage = d.get("usage")
    if not isinstance(usage, dict):
        return "-"
    u = cast(dict[str, Any], usage)
    inp = u.get("prompt_tokens") or u.get("input_tokens")
    out = u.get("completion_tokens") or u.get("output_tokens")
    if inp is None and out is None:
        return "-"
    return f"{inp or '?'}/{out or '?'}"


def _body_summary(entry: CassetteEntry) -> str:
    if entry.response.stream_chunks is not None:
        return f"{len(entry.response.stream_chunks)} streamed chunks"
    body = entry.response.body
    if body is None:
        return "(empty)"
    if isinstance(body, dict | list):
        return _truncate(json.dumps(body, ensure_ascii=False), 80)
    return _truncate(str(body), 80)


def _pretty_json(value: Any) -> str:
    """Pretty-print JSON-y values; fall back to ``repr`` for non-JSON content."""
    if value is None:
        return "(empty)"
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


# ─── Route handlers ────────────────────────────────────────────────────


def _state(request: Request) -> tuple[Cassette, Environment]:
    return request.app.state.cassette, request.app.state.jinja


async def index(request: Request) -> Response:
    """Render the main page with the filter form and an initial row table."""
    cassette, env = _state(request)
    entries = cassette.entries()
    spec = _build_filter_spec(dict(request.query_params))
    rows = list(_iter_filtered_rows(entries, spec))
    template = env.get_template("index.html")
    html = template.render(
        cassette_path=str(cassette.path),
        total=len(entries),
        rows=rows,
        matched=len(rows),
        filters={
            "provider": spec.provider or "",
            "model": spec.model or "",
            "status": spec.status or "",
            "has_tool_call": _bool_to_form(spec.has_tool_call),
            "regex": request.query_params.get("regex") or "",
            "limit": "" if spec.limit is None else str(spec.limit),
        },
    )
    return HTMLResponse(html)


async def entries_fragment(request: Request) -> Response:
    """Return only the rows table fragment — the HTMX swap target."""
    cassette, env = _state(request)
    entries = cassette.entries()
    spec = _build_filter_spec(dict(request.query_params))
    rows = list(_iter_filtered_rows(entries, spec))
    template = env.get_template("_rows.html")
    html = template.render(rows=rows, matched=len(rows), total=len(entries))
    return HTMLResponse(html)


async def entry_detail(request: Request) -> Response:
    """Render the full detail page for a single entry by cassette index."""
    cassette, env = _state(request)
    raw_idx = request.path_params["idx"]
    try:
        idx = int(raw_idx)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail=f"entry idx must be an int: {raw_idx!r}"
        ) from exc

    entries = cassette.entries()
    if idx < 0 or idx >= len(entries):
        raise HTTPException(status_code=404, detail=f"entry #{idx} not found")
    entry = entries[idx]
    template = env.get_template("entry.html")
    html = template.render(
        cassette_path=str(cassette.path),
        idx=idx,
        total=len(entries),
        entry=entry,
        model=_model_name(entry) or "-",
        status_class=_status_class(entry.response.status),
        tokens=_tokens_summary(entry),
        is_stream=entry.response.stream_chunks is not None,
    )
    return HTMLResponse(html)


def _bool_to_form(value: bool | None) -> str:
    """Render an Optional[bool] for an HTML ``<select>``: '', 'true', or 'false'."""
    if value is None:
        return ""
    return "true" if value else "false"


# ─── App factory + lifespan ────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: Starlette, cassette_path: Path) -> AsyncGenerator[None]:
    """Load the cassette once at startup; the in-memory store survives the request loop."""
    app.state.cassette = Cassette(cassette_path)
    app.state.jinja = _build_jinja_env()
    yield


def create_app(cassette_path: Path) -> Starlette:
    """Build the inspector ASGI app pinned to ``cassette_path``.

    Raises:
        FileNotFoundError: if ``cassette_path`` does not exist. Failing fast
            here gives the CLI a clean error message before uvicorn binds a
            port — a friendlier UX than a 500 on the first browser request.
    """
    path = Path(cassette_path)
    if not path.exists():
        raise FileNotFoundError(f"cassette not found: {path}")

    routes = [
        Route("/", index, methods=["GET"]),
        Route("/entries", entries_fragment, methods=["GET"]),
        Route("/entries/{idx}", entry_detail, methods=["GET"]),
        Mount("/static", app=StaticFiles(directory=str(_STATIC_DIR)), name="static"),
    ]
    app = Starlette(
        routes=routes,
        lifespan=functools.partial(_lifespan, cassette_path=path),
    )
    # Mirror lifespan state for code paths (tests) that read attrs before a
    # request triggers lifespan startup — TestClient handles lifespan, but
    # keeping these here makes the contract explicit.
    app.state.cassette_path = path
    return app


def serve(
    cassette_path: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    """Run the inspector synchronously (blocks the calling thread)."""
    app = create_app(cassette_path)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
