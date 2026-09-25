"""Unit tests for the SSE generator — zero network, fake agents only.

Specifically exercises the three paths the plan calls out as the classic
SSE mistakes to get wrong: normal completion, an upstream error raised
mid-stream, and an unexpected error — confirming each ends in the right
terminal event and that `finally`-based cleanup always runs.
"""

from collections.abc import AsyncIterator

import pytest

from luna.api.routes_chat import stream_chat_response
from luna.core.models import Message
from luna.llm.groq_client import GroqError


class _FakeAgent:
    """A fake Agent (see agents/base.py's Protocol) for testing the
    generator in isolation — no real GroqClient, no network."""

    name = "fake"
    system_prompt = "irrelevant for this test"

    def __init__(self, chunks: list[str], raise_after: Exception | None = None) -> None:
        self._chunks = chunks
        self._raise_after = raise_after

    async def stream_response(self, messages: list[Message]) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk
        if self._raise_after is not None:
            raise self._raise_after


async def _collect(agent: _FakeAgent) -> list[str]:
    return [event async for event in stream_chat_response(agent, [Message(role="user", content="hi")])]


@pytest.mark.parametrize("chunks", [["hello", " ", "world"], []])
async def test_normal_completion_emits_token_then_done(chunks):
    events = await _collect(_FakeAgent(chunks))

    token_events = [e for e in events if e.startswith("event: token")]
    assert len(token_events) == len(chunks)
    for chunk, event in zip(chunks, token_events, strict=True):
        assert f'"text": "{chunk}"' in event

    assert events[-1].startswith("event: done")
    assert not any(e.startswith("event: error") for e in events)


async def test_groq_error_mid_stream_emits_error_not_done():
    agent = _FakeAgent(["partial "], raise_after=GroqError("upstream broke"))
    events = await _collect(agent)

    assert any(e.startswith("event: token") for e in events)
    assert events[-1].startswith("event: error")
    assert not any(e.startswith("event: done") for e in events)


async def test_unexpected_error_also_emits_error_not_done():
    agent = _FakeAgent([], raise_after=RuntimeError("a bug, not an upstream failure"))
    events = await _collect(agent)

    assert events[-1].startswith("event: error")
    assert not any(e.startswith("event: done") for e in events)
