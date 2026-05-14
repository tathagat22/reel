"""SDK adapters — ``@cassette`` decorator and pytest plugin.

Public entry points:

* :func:`reel.cassette` — decorator for test functions
* :func:`reel.proxy_context` — context manager equivalent for non-pytest code
"""

from reel.sdk.cassette import ProxyHandle, cassette, proxy_context

__all__ = ["ProxyHandle", "cassette", "proxy_context"]
