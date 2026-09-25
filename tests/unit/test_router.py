"""Unit tests for AgentRouter's fast-path/slow-path split — the actual
cost-governance behavior: a fake `classify` that COUNTS its own calls
proves the LLM classifier is skipped entirely when the heuristic is
confident, and only invoked when it isn't."""

from luna.routing.router import AgentRouter


def _counting_classifier(response: str = "product"):
    calls = {"count": 0}

    async def classify(_message: str) -> str:
        calls["count"] += 1
        return response

    return classify, calls


async def test_confident_heuristic_never_calls_the_classifier():
    classify, calls = _counting_classifier()
    router = AgentRouter(classify=classify, confidence_threshold=0.6)

    decision = await router.route("I have a bug in my python code, getting a traceback")

    assert decision.agent_name == "coding"
    assert decision.method == "heuristic"
    assert calls["count"] == 0


async def test_low_confidence_heuristic_falls_back_to_classifier():
    classify, calls = _counting_classifier(response="product")
    router = AgentRouter(classify=classify, confidence_threshold=0.6)

    # "the server has a bug" splits evenly between infra/coding keywords
    # (confidence 0.5) — below the 0.6 threshold, so this MUST fall back.
    decision = await router.route("the server has a bug")

    assert decision.agent_name == "product"
    assert decision.method == "llm_classifier"
    assert calls["count"] == 1


async def test_threshold_is_configurable():
    classify, calls = _counting_classifier()
    # A threshold of 0.0 means even a low-confidence heuristic guess is
    # always accepted — the classifier should never be needed.
    router = AgentRouter(classify=classify, confidence_threshold=0.0)

    decision = await router.route("the server has a bug")

    assert decision.method == "heuristic"
    assert calls["count"] == 0
