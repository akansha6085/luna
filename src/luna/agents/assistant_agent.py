"""Phase 1's one agent — the template Phase 2's other agents will copy.

Deliberately just a name, a system prompt, and a model choice wired to
the shared GroqClient. When coding_agent / infra_agent / product_agent
show up in Phase 2, this is the shape they'll all have.
"""

from collections.abc import AsyncIterator

from luna.core.models import Message
from luna.llm.groq_client import GroqClient


class AssistantAgent:
    name = "assistant"
    system_prompt = "You are Luna, a helpful, concise general-purpose assistant."
    # A small, fast model is the right default for a general chat agent —
    # cheap and fast wins when there's no reason yet to pay for a bigger
    # one. Verified against this key's actual `client.models.list()` —
    # the groq SDK's bundled type hints for `model` list names (like
    # llama-3.1-8b-instant) that are already gone from Groq's real catalog,
    # a genuine "don't trust a vendor SDK's stale literal list, check the
    # live API" lesson.
    model = "openai/gpt-oss-20b"

    def __init__(self, groq_client: GroqClient) -> None:
        self._groq_client = groq_client

    async def stream_response(self, messages: list[Message]) -> AsyncIterator[str]:
        full_messages = [Message(role="system", content=self.system_prompt), *messages]
        async for chunk in self._groq_client.stream_chat(full_messages, model=self.model):
            yield chunk
