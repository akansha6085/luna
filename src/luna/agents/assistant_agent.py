"""The default/general-purpose agent — used when routing isn't confident
the message belongs to a specialized domain (coding/infra/product)."""

from luna.agents.base import SimpleAgent


class AssistantAgent(SimpleAgent):
    name = "assistant"
    system_prompt = "You are Luna, a helpful, concise general-purpose assistant."
    # Verified against this key's actual `client.models.list()` — the groq
    # SDK's bundled type hints list names (like llama-3.1-8b-instant) that
    # are already gone from Groq's real catalog. Don't trust a vendor
    # SDK's stale literal list; check the live API.
    model = "openai/gpt-oss-20b"
