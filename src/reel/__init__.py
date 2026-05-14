"""Reel — VCR for LLM APIs.

Public test-side API lives at :mod:`reel.sdk` — the canonical import is::

    from reel.sdk import cassette

(The top-level ``reel`` namespace intentionally does **not** re-export
``cassette`` because the internal :mod:`reel.cassette` sub-package — which
holds schema, reader, writer — already owns that attribute slot.)
"""

__version__ = "0.0.1"

__all__ = ["__version__"]
