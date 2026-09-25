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


class Agent(Protocol):
    name: str
    system_prompt: str

    def stream_response(self, messages: list[Message]) -> AsyncIterator[str]:
        """Stream this agent's response as a sequence of text chunks."""
        ...
