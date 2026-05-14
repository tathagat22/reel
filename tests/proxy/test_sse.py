"""Sprint 2.1 — incremental SSE parser tests."""

from __future__ import annotations

from reel.proxy.sse import SSEEvent, SSEParser


def _events(parser: SSEParser, *chunks: bytes) -> list[SSEEvent]:
    out: list[SSEEvent] = []
    for chunk in chunks:
        out.extend(parser.feed(chunk))
    out.extend(parser.close())
    return out


def test_single_event() -> None:
    events = _events(SSEParser(), b"data: hello\n\n")
    assert events == [SSEEvent(data="hello")]


def test_two_events() -> None:
    events = _events(SSEParser(), b"data: a\n\ndata: b\n\n")
    assert events == [SSEEvent(data="a"), SSEEvent(data="b")]


def test_split_across_chunks_recombines() -> None:
    """The classic test: bytes split anywhere reassemble into the right events."""
    parser = SSEParser()
    events: list[SSEEvent] = []
    payload = b"data: hello world\n\ndata: second\n\n"
    # Feed one byte at a time — pathological but proves byte-level correctness.
    for i in range(len(payload)):
        events.extend(parser.feed(payload[i : i + 1]))
    events.extend(parser.close())
    assert events == [SSEEvent(data="hello world"), SSEEvent(data="second")]


def test_crlf_line_endings() -> None:
    events = _events(SSEParser(), b"data: hello\r\n\r\n")
    assert events == [SSEEvent(data="hello")]


def test_mixed_line_endings() -> None:
    events = _events(SSEParser(), b"data: line1\r\ndata: line2\n\r\n")
    assert events == [SSEEvent(data="line1\nline2")]


def test_comment_lines_ignored() -> None:
    events = _events(SSEParser(), b": this is a comment\ndata: real\n\n")
    assert events == [SSEEvent(data="real")]


def test_multiple_data_lines_joined_with_newline() -> None:
    events = _events(SSEParser(), b"data: line1\ndata: line2\ndata: line3\n\n")
    assert events == [SSEEvent(data="line1\nline2\nline3")]


def test_event_type_field() -> None:
    events = _events(
        SSEParser(),
        b"event: message_start\ndata: {}\n\n",
    )
    assert events == [SSEEvent(data="{}", event="message_start")]


def test_event_id_field() -> None:
    events = _events(SSEParser(), b"id: 123\ndata: hello\n\n")
    assert events == [SSEEvent(data="hello", id="123")]


def test_retry_field_parsed_as_int() -> None:
    events = _events(SSEParser(), b"retry: 5000\ndata: hello\n\n")
    assert events == [SSEEvent(data="hello", retry=5000)]


def test_retry_field_with_non_int_value_ignored() -> None:
    events = _events(SSEParser(), b"retry: not-a-number\ndata: hello\n\n")
    assert events == [SSEEvent(data="hello")]


def test_event_without_data_is_dropped() -> None:
    events = _events(SSEParser(), b"event: only-meta\n\n")
    assert events == []


def test_done_sentinel_is_just_another_event() -> None:
    events = _events(SSEParser(), b"data: {}\n\ndata: [DONE]\n\n")
    assert events == [SSEEvent(data="{}"), SSEEvent(data="[DONE]")]


def test_value_strips_single_leading_space_only() -> None:
    """`data:hello` and `data: hello` produce the same value, but `data:  hi` keeps one space."""
    events = _events(SSEParser(), b"data:hello\n\ndata:  hi\n\n")
    assert events == [SSEEvent(data="hello"), SSEEvent(data=" hi")]


def test_realistic_openai_stream() -> None:
    """A small but realistic OpenAI chat-completions streaming chunk sequence."""
    parser = SSEParser()
    raw = (
        b'data: {"choices":[{"delta":{"role":"assistant","content":""}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b'data: [DONE]\n\n'
    )
    events = list(parser.feed(raw)) + list(parser.close())
    assert len(events) == 4
    assert events[0].data.startswith('{"choices":[{"delta":{"role":"assistant"')
    assert '"Hello"' in events[1].data
    assert '" world"' in events[2].data
    assert events[3].data == "[DONE]"


def test_unterminated_event_flushes_on_close() -> None:
    """If the stream ends without a final blank line, the in-progress event still flushes."""
    parser = SSEParser()
    events = list(parser.feed(b"data: incomplete"))
    assert events == []  # no blank line yet
    events = list(parser.close())
    assert events == [SSEEvent(data="incomplete")]
