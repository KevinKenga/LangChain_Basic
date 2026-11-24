"""
Offline tests for the grader and the retry loop.

The grader's free check runs for real; its model call is mocked. The loop is
exercised through the real wiring in graph/build_graph.py, with the working
steps replaced by stubs -- so the edges, the attempt counter and the stop
condition are the ones the app actually uses.
"""

import uuid                                     # unique run ids

import pytest                                   # the test runner

from graph import build_graph as graph_module   # the wiring, with nodes we can swap out
from graph import grader                        # the grader under test
from graph.grader import (                      # the pieces under test
    EMPTY_SEARCH,
    INSUFFICIENT,
    SUFFICIENT,
    UNAVAILABLE,
    check_evidence,
    empty_searches,
)
from graph.state import create_initial_state    # a fresh state
from guardrails.factual import GROUNDED         # the verdict that means "no review needed"

RESULTS = {"risk_register · FY2026": [{"text": "Kestrel is single-sourced."}]}


# ------------------------------------------------------------------------------
# The free empty-search check
# ------------------------------------------------------------------------------

def test_empty_search_is_caught_without_a_model_call(monkeypatch):
    monkeypatch.setattr(grader, "model_verdict", lambda *a: pytest.fail("Azure was called"))
    results = {"annual_review · FY2025": [], "annual_review · FY2026": [{"text": "OTIF was 93.4 per cent."}]}
    verdict = check_evidence("How did OTIF change?", results)
    assert verdict.sufficient is False
    assert verdict.verdict == INSUFFICIENT
    assert verdict.source == EMPTY_SEARCH
    assert "annual_review · FY2025" in verdict.missing


def test_empty_searches_lists_every_empty_search():
    assert empty_searches({"a · FY2025": [], "b · FY2026": [{"text": "t"}], "c · FY2026": []}) == \
        ["a · FY2025", "c · FY2026"]


def test_no_empty_search_asks_the_model(monkeypatch):
    monkeypatch.setattr(grader, "model_verdict", lambda q, r: grader.GraderVerdict(sufficient=True))
    assert check_evidence("q", RESULTS).sufficient is True


# ------------------------------------------------------------------------------
# A failed grader call counts as sufficient
# ------------------------------------------------------------------------------

def test_failed_grader_call_is_treated_as_sufficient(monkeypatch):
    def boom(*args):
        raise RuntimeError("no key")

    monkeypatch.setattr(grader, "model_verdict", boom)
    verdict = check_evidence("q", RESULTS)
    assert verdict.sufficient is True           # proceed rather than loop
    assert verdict.verdict == UNAVAILABLE       # but say so, for the logs


def test_unusable_grader_json_is_treated_as_sufficient(monkeypatch):
    from types import SimpleNamespace

    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reply)))
    monkeypatch.setattr("azure_clients.openai_client", lambda: fake)  # grader imports it at call time
    assert check_evidence("q", RESULTS).verdict == UNAVAILABLE


# ------------------------------------------------------------------------------
# The retry loop, through the real wiring
# ------------------------------------------------------------------------------

def stub_pipeline(monkeypatch, calls, sufficient):
    """Replace every working node with a stub; keep the real edges, attempt counter and stop condition."""
    monkeypatch.setattr(graph_module, "input_guardrail_node", lambda s: {"input_allowed": True})
    monkeypatch.setattr(graph_module, "route_node", lambda s: {
        "intent": "lookup",
        "plan": [{"doc_type": "risk_register", "fiscal_year": "FY2026"}],
        "plan_reason": "stub",
        "attempts": 0,
        "rewritten_query": None,
    })

    def fake_retrieve(state):
        calls["retrieve"] += 1                  # count every retrieval attempt
        return {"candidate_chunks": RESULTS, "attempts": state.get("attempts", 0) + 1}

    monkeypatch.setattr(graph_module, "retrieve_node", fake_retrieve)
    monkeypatch.setattr(graph_module, "rerank_node", lambda s: {"reranked_chunks": s["candidate_chunks"]})
    monkeypatch.setattr(graph_module, "grade_node", lambda s: {
        "grader_sufficient": sufficient,
        "grader_verdict": SUFFICIENT if sufficient else INSUFFICIENT,
        "grader_missing": "" if sufficient else "the risk score",
        "grader_better_query": None if sufficient else "Kestrel risk score",
        "rewritten_query": None if sufficient else "Kestrel risk score",
    })

    def fake_generate(state):
        calls["generate"] += 1                  # count the generation
        return {"draft_answer": "Kestrel is single-sourced [1]."}

    monkeypatch.setattr(graph_module, "generate_node", fake_generate)
    monkeypatch.setattr(graph_module, "output_guardrail_node",
                        lambda s: {"grounding_verdict": GROUNDED, "review_required": False})


def run_graph():
    """Run the stubbed pipeline once and return (final state, thread)."""
    graph = graph_module.build_graph()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    return graph.invoke(create_initial_state("q"), thread), thread


def test_retry_loop_stops_after_two_attempts(monkeypatch):
    calls = {"retrieve": 0, "generate": 0}
    stub_pipeline(monkeypatch, calls, sufficient=False)  # the grader never has enough
    state, _ = run_graph()

    assert calls["retrieve"] == 2               # exactly two retrieval attempts, never three
    assert calls["generate"] == 1               # and the graph still proceeded to generate
    assert state["attempts"] == 2
    assert state["final_answer"] == "Kestrel is single-sourced [1]."


def test_sufficient_evidence_generates_after_one_attempt(monkeypatch):
    calls = {"retrieve": 0, "generate": 0}
    stub_pipeline(monkeypatch, calls, sufficient=True)
    state, _ = run_graph()

    assert calls["retrieve"] == 1               # no retry when the evidence is enough
    assert calls["generate"] == 1
    assert state["attempts"] == 1
