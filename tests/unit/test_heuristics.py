"""Table-driven tests for the pure heuristic router — no I/O, no mocking
needed, which is the entire point of keeping heuristics.py a pure function."""

import pytest

from luna.routing.heuristics import heuristic_route


@pytest.mark.parametrize(
    ("message", "expected_agent"),
    [
        ("I'm getting a null pointer exception in my python function", "coding"),
        ("can you help me debug this stack trace?", "coding"),
        ("the kubernetes pod keeps crash looping after every deploy", "infra"),
        ("our aws cluster latency spiked, check the logs", "infra"),
        ("can we add this to the roadmap for the next release?", "product"),
        ("what's the pricing strategy for this feature launch?", "product"),
        ("hi there, how are you today?", "assistant"),
        ("thanks so much!", "assistant"),
    ],
)
def test_routes_to_expected_agent(message, expected_agent):
    decision = heuristic_route(message)
    assert decision.agent_name == expected_agent
    assert decision.method == "heuristic"


def test_no_keyword_match_is_high_confidence_default():
    # Nothing technical here — that absence of signal IS the signal, so
    # this should be a confident default, not a low-confidence guess.
    decision = heuristic_route("good morning!")
    assert decision.agent_name == "assistant"
    assert decision.confidence == 1.0


def test_clear_single_category_match_is_high_confidence():
    decision = heuristic_route("I have a bug in my python code, getting a traceback")
    assert decision.agent_name == "coding"
    assert decision.confidence > 0.6


def test_ambiguous_message_across_categories_is_low_confidence():
    # "bug" -> coding, "server" -> infra: an even split should read as
    # genuinely ambiguous (low confidence), which is exactly what should
    # trigger the LLM-classifier fallback in router.py.
    decision = heuristic_route("the server has a bug")
    assert decision.confidence == pytest.approx(0.5)
