"""Pure, zero-I/O routing: a weighted keyword scorer.

No network, no DB access, on purpose. This is the "free, instant" first
pass the router (router.py) always tries before ever considering a paid
LLM call (llm_classifier.py) — and it's exactly why this function is
trivially unit-testable as a flat table of (input, expected_agent) pairs
with no mocking required (see tests/unit/test_heuristics.py).
"""

from dataclasses import dataclass

AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coding": (
        "bug", "error", "exception", "stack trace", "traceback", "function",
        "class", "refactor", "unit test", "code", "python", "javascript",
        "compile", "syntax", "algorithm", "debug", "null pointer",
    ),
    "infra": (
        "kubernetes", "k8s", "pod", "deploy", "deployment", "docker",
        "container", "server", "outage", "cpu", "memory", "latency",
        "network", "dns", "aws", "cluster", "crash loop", "restart",
        "kubectl", "helm", "prometheus", "logs",
    ),
    "product": (
        "feature", "roadmap", "customer", "user story", "requirement",
        "pricing", "launch", "release notes", "design review", "ux",
        "persona", "backlog", "stakeholder",
    ),
}

# The agent used when nothing matches, or when the match is genuinely
# ambiguous between categories.
DEFAULT_AGENT = "assistant"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    agent_name: str
    method: str  # "heuristic" | "llm_classifier"
    confidence: float


def heuristic_route(message: str) -> RoutingDecision:
    text = message.lower()
    scores = {
        agent: sum(1 for keyword in keywords if keyword in text)
        for agent, keywords in AGENT_KEYWORDS.items()
    }

    best_agent = max(scores, key=lambda agent: scores[agent])
    best_score = scores[best_agent]

    if best_score == 0:
        # Nothing matched any specialized category — that itself IS the
        # signal: this reads as general chit-chat, not a technical
        # question, so default confidently rather than escalating to a
        # paid LLM call for the common "hi" / "thanks" / small-talk case.
        return RoutingDecision(agent_name=DEFAULT_AGENT, method="heuristic", confidence=1.0)

    # Confidence = how dominant the winning category is relative to ALL
    # keyword signal found, across every category. A tie (e.g. coding=2,
    # infra=2) naturally produces a low confidence (2/4 = 0.5) without any
    # special-case tie-breaking code — the formula already captures
    # "ambiguous" as "low confidence," which is what should trigger the
    # LLM-classifier fallback in router.py.
    total_signal = sum(scores.values())
    confidence = best_score / total_signal
    return RoutingDecision(agent_name=best_agent, method="heuristic", confidence=confidence)
