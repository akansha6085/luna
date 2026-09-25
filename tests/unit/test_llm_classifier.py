"""Unit tests for the LLM-classifier fallback's parsing logic — a fake
`ClassifyFn` stands in for a real Groq call, so this never touches the
network. classify_with_groq (the real Groq-backed implementation) is
exercised only by a small integration test, not here."""

from luna.routing.llm_classifier import llm_classify_route


async def test_valid_category_is_used_verbatim():
    async def fake_classify(_message: str) -> str:
        return "infra"

    decision = await llm_classify_route("some message", fake_classify)
    assert decision.agent_name == "infra"
    assert decision.method == "llm_classifier"


async def test_category_is_case_and_whitespace_insensitive():
    async def fake_classify(_message: str) -> str:
        return "  Coding\n"

    decision = await llm_classify_route("some message", fake_classify)
    assert decision.agent_name == "coding"


async def test_unrecognized_response_falls_back_to_assistant():
    async def fake_classify(_message: str) -> str:
        return "I'm not sure, maybe something else entirely"

    decision = await llm_classify_route("some message", fake_classify)
    assert decision.agent_name == "assistant"
