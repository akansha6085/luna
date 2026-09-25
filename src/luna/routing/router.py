"""AgentRouter: fast heuristic path, LLM-classifier fallback on low confidence.

This is the "spend money only when genuinely unsure" pattern — the same
cost-governance idea the whole Luna project is inspired by (see the
project README), implemented for real instead of just described. The
heuristic (heuristics.py) is always tried first, free and instant; the
LLM classifier (llm_classifier.py) only runs when the heuristic's
confidence falls below `confidence_threshold` — configurable via
Settings.routing_confidence_threshold, i.e. tunable via the K8s
ConfigMap without a rebuild.
"""

from luna.routing.heuristics import RoutingDecision, heuristic_route
from luna.routing.llm_classifier import ClassifyFn, llm_classify_route


class AgentRouter:
    def __init__(self, classify: ClassifyFn, confidence_threshold: float) -> None:
        self._classify = classify
        self._confidence_threshold = confidence_threshold

    async def route(self, message: str) -> RoutingDecision:
        decision = heuristic_route(message)
        if decision.confidence >= self._confidence_threshold:
            return decision
        return await llm_classify_route(message, self._classify)
