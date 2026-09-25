"""LLM-based routing fallback — used only when the heuristic isn't confident.

Deliberately takes an injected async callable (`ClassifyFn`), not a
GroqClient directly — so the parsing/decision logic here (turning a raw
model response into a RoutingDecision, including the "model said
something we don't recognize" fallback) is unit-tested against a fake
function returning canned strings, with zero real network calls. Only a
small number of integration tests hit the real Groq API to confirm the
concrete `classify_with_groq` wrapper below actually works end to end.
"""

from collections.abc import Awaitable, Callable

from luna.core.models import Message
from luna.llm.groq_client import GroqClient
from luna.routing.heuristics import RoutingDecision

VALID_CATEGORIES = ("coding", "infra", "product", "assistant")

CLASSIFIER_MODEL = "openai/gpt-oss-20b"

ClassifyFn = Callable[[str], Awaitable[str]]


async def llm_classify_route(message: str, classify: ClassifyFn) -> RoutingDecision:
    raw = await classify(message)
    category = raw.strip().lower()
    if category not in VALID_CATEGORIES:
        # The model didn't answer with a category we recognize — fail
        # safe to the general agent rather than propagate a bad category
        # name into the registry lookup in api/routes_chat.py.
        category = "assistant"
    return RoutingDecision(agent_name=category, method="llm_classifier", confidence=1.0)


async def classify_with_groq(groq_client: GroqClient, message: str) -> str:
    """The concrete `ClassifyFn` used in production — a single cheap,
    non-streaming completion (see GroqClient.complete) asking for one
    category word."""
    prompt = (
        "Classify the following user message into exactly one category: "
        "coding, infra, product, or assistant. Reply with only that one "
        f"word, nothing else.\n\nMessage: {message}"
    )
    return await groq_client.complete([Message(role="user", content=prompt)], model=CLASSIFIER_MODEL)
