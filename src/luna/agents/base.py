"""The Agent abstraction — the Strategy pattern seam.

An Agent is nothing more than a name, a system prompt, and a way to
stream a response given message history. Concrete agents (Phase 2 adds
coding/infra/product agents alongside Phase 1's one) differ ONLY in
these — which is what makes adding a new agent later a matter of writing
one small new file plus one line in registry.py, with nothing in
routing/ or api/ needing to change (the open-closed principle, made
concrete rather than abstract).
"""

from collections.abc import AsyncIterator
from typing import Protocol

from luna.core.models import Message
from luna.llm.groq_client import GroqClient


class Agent(Protocol):
    name: str
    system_prompt: str

    def stream_response(self, messages: list[Message]) -> AsyncIterator[str]:
        """Stream this agent's response as a sequence of text chunks."""
        ...


class SimpleAgent:
    """Concrete base for the common case: an agent that differs from any
    other agent ONLY in name/system_prompt/model, with no extra behavior
    (no retrieval, no tools, nothing). Every Phase 2 agent is one of these.

    Not required by the Agent Protocol above — a future agent with
    genuinely different behavior (Phase 5's RAG-enabled agent, say) can
    just implement the Protocol directly instead of inheriting this. The
    Protocol is the contract; this is just one convenient implementation
    of it, which is why routing/ and api/ only ever type against `Agent`.
    """

    name: str
    system_prompt: str
    model: str

    def __init__(self, groq_client: GroqClient) -> None:
        self._groq_client = groq_client

    async def stream_response(self, messages: list[Message]) -> AsyncIterator[str]:
        full_messages = [Message(role="system", content=self.system_prompt), *messages]
        async for chunk in self._groq_client.stream_chat(full_messages, model=self.model):
            yield chunk
