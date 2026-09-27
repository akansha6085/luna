"""Unit tests for the SSE generator — zero network, zero database, fake
agents and repos only.

Specifically exercises the paths that matter: `conversation` and `routed`
are always the first two events, then normal completion, an upstream
error raised mid-stream, and an unexpected error — confirming each ends
in the right terminal event, that `finally`-based cleanup (including the
"persist even on error" behavior) always runs, and that a normal
completion actually calls the repos to persist + touch.
"""

import uuid
from collections.abc import AsyncIterator

import pytest

from luna.api.routes_chat import stream_chat_response
from luna.core.models import Message
from luna.llm.groq_client import GroqError
from luna.routing.heuristics import RoutingDecision

_DECISION = RoutingDecision(agent_name="fake", method="heuristic", confidence=0.9)
_CONVERSATION_ID = uuid.uuid4()


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


class _FakeMessageRepo:
    """Records calls instead of touching a database — lets tests assert
    "was the assistant's message actually persisted" without Postgres."""

    def __init__(self) -> None:
        self.added: list[dict[str, object]] = []

    async def add(self, conversation_id, role, content, agent_name=None, finish_reason=None):
        self.added.append(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "agent_name": agent_name,
                "finish_reason": finish_reason,
            }
        )


class _FakeConversationRepo:
    def __init__(self) -> None:
        self.touched: list[object] = []

    async def touch(self, conversation_id):
        self.touched.append(conversation_id)


async def _collect(agent: _FakeAgent, message_repo=None, conversation_repo=None) -> list[str]:
    message_repo = message_repo or _FakeMessageRepo()
    conversation_repo = conversation_repo or _FakeConversationRepo()
    return [
        event
        async for event in stream_chat_response(
            agent,
            [Message(role="user", content="hi")],
            _DECISION,
            _CONVERSATION_ID,
            message_repo,
            conversation_repo,
        )
    ]


async def test_conversation_then_routed_are_always_first():
    events = await _collect(_FakeAgent(["hi"]))
    assert events[0].startswith("event: conversation")
    assert str(_CONVERSATION_ID) in events[0]
    assert events[1].startswith("event: routed")
    assert '"agent": "fake"' in events[1]
    assert '"method": "heuristic"' in events[1]


@pytest.mark.parametrize("chunks", [["hello", " ", "world"], []])
async def test_normal_completion_emits_token_then_done(chunks):
    events = await _collect(_FakeAgent(chunks))

    token_events = [e for e in events if e.startswith("event: token")]
    assert len(token_events) == len(chunks)
    for chunk, event in zip(chunks, token_events, strict=True):
        assert f'"text": "{chunk}"' in event

    assert events[-1].startswith("event: done")
    assert not any(e.startswith("event: error") for e in events)


async def test_normal_completion_persists_assistant_message_and_touches_conversation():
    message_repo = _FakeMessageRepo()
    conversation_repo = _FakeConversationRepo()
    await _collect(_FakeAgent(["hello", " world"]), message_repo, conversation_repo)

    assert len(message_repo.added) == 1
    saved = message_repo.added[0]
    assert saved["role"] == "assistant"
    assert saved["content"] == "hello world"
    assert saved["agent_name"] == "fake"
    assert saved["finish_reason"] == "stop"
    assert conversation_repo.touched == [_CONVERSATION_ID]


async def test_empty_response_is_not_persisted():
    # No tokens ever arrived (e.g. the model returned nothing) — nothing
    # meaningful to save, and nothing for a reload to show either way.
    message_repo = _FakeMessageRepo()
    await _collect(_FakeAgent([]), message_repo)
    assert message_repo.added == []


async def test_groq_error_mid_stream_emits_error_not_done_but_still_persists_partial_text():
    message_repo = _FakeMessageRepo()
    agent = _FakeAgent(["partial "], raise_after=GroqError("upstream broke"))
    events = await _collect(agent, message_repo)

    assert any(e.startswith("event: token") for e in events)
    assert events[-1].startswith("event: error")
    assert not any(e.startswith("event: done") for e in events)
    assert message_repo.added[0]["content"] == "partial "
    assert message_repo.added[0]["finish_reason"] == "error"


async def test_unexpected_error_also_emits_error_not_done():
    agent = _FakeAgent([], raise_after=RuntimeError("a bug, not an upstream failure"))
    events = await _collect(agent)

    assert events[-1].startswith("event: error")
    assert not any(e.startswith("event: done") for e in events)
