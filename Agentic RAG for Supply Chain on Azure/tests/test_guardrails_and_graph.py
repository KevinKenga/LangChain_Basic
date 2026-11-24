"""
Offline tests for the guardrails and the human-review pause.
"""

import uuid                                     # unique run ids

import numpy as np                              # fixed vectors for the similarity check
import pytest                                   # the test runner

from graph import build_graph as graph_module   # the wiring, with nodes we can swap out
from graph.state import create_initial_state    # a fresh state
from guardrails import factual, topic           # grounding and the topic check
from guardrails.factual import (                # the pieces under test
    GROUNDED,
    NEEDS_REVIEW,
    GroundingDecision,
    check_grounding,
    check_numbers,
    collect_source_texts,
    strip_citations,
)
from guardrails.format import check_format      # format
from guardrails.safety import ALLOW, BLOCK, check_safety  # safety

SOURCES = {
    "FY2025": ["Customer OTIF stood at 91.2 per cent."],
    "FY2026": ["Customer OTIF stood at 93.4 per cent."],
}


# --- grounding ---------------------------------------------------------------

def test_citation_markers_are_not_read_as_figures():
    d = check_numbers("In FY2025 OTIF was 91.2 per cent [1].", SOURCES)
    assert d.verdict == GROUNDED and d.unsupported_items == []   # [1] is a citation, not the figure 1


def test_citation_marker_alone_adds_no_number():
    stripped = strip_citations("OTIF was 91.2 per cent [3].")
    assert "[3]" not in stripped and "3" not in stripped   # the marker and its digit are gone
    d = check_numbers("OTIF was 91.2 per cent [3].", SOURCES)
    assert d.verdict == GROUNDED


def test_wrong_year_figure_is_caught():
    d = check_numbers("In FY2026 OTIF was 91.2 per cent [2].", SOURCES)
    assert d.verdict == NEEDS_REVIEW and "attributed to FY2026" in d.unsupported_items[0]


def test_heading_year_applies_to_lines_below():
    d = check_numbers("What FY2026 said:\n- OTIF was 91.2 per cent [1].", SOURCES)
    assert d.verdict == NEEDS_REVIEW


def test_plain_statement_needs_no_azure_call(monkeypatch):
    monkeypatch.setattr(factual, "check_claims", lambda *a: pytest.fail("Azure was called"))
    assert check_grounding("In FY2025 OTIF was 91.2 per cent [1].", SOURCES).verdict == GROUNDED


def test_comparison_always_gets_the_claims_check(monkeypatch):
    calls = []
    monkeypatch.setattr(factual, "check_claims",
                        lambda a, s: calls.append(1) or GroundingDecision(NEEDS_REVIEW, "claims", "stub"))
    check_grounding("OTIF rose from 91.2 per cent in FY2025 to 93.4 per cent in FY2026 [1][2].", SOURCES)
    assert calls == [1]


def test_sources_are_grouped_by_year_whichever_search_found_them():
    reranked = {
        "annual_review · FY2026": [{"text": "OTIF was 93.4 per cent.", "fiscal_year": "FY2026"}],
        "risk_register · FY2026": [{"text": "Kestrel is single-sourced.", "fiscal_year": "FY2026"}],
        "annual_review · FY2025": [{"text": "OTIF was 91.2 per cent.", "fiscal_year": "FY2025"}],
    }
    grouped = collect_source_texts(reranked)
    assert sorted(grouped) == ["FY2025", "FY2026"]                  # two years, not three searches
    assert len(grouped["FY2026"]) == 2                              # both FY2026 chunks landed together


# --- safety, topic, format ---------------------------------------------------

@pytest.mark.parametrize("q", ["Should we terminate Kestrel Semiconductors?",   # Q13
                               "What is the status of the supplier with PAN ABCDE1234F?"])  # Q14
def test_unsafe_questions_are_blocked(q):
    assert check_safety(q).verdict == BLOCK


def test_sourcing_decision_is_named_in_the_reason():
    assert check_safety("Should we blacklist the supplier?").check == "sourcing_decision"


def test_ordinary_question_is_safe():
    assert check_safety("What is the risk score of Kestrel Semiconductors?").verdict == ALLOW


def test_keyword_question_needs_no_azure_call(monkeypatch):
    monkeypatch.setattr(topic, "check_by_similarity", lambda q: pytest.fail("Azure was called"))
    assert topic.check_topic("How did customer OTIF change?").verdict == topic.ALLOW


def test_off_topic_question_is_blocked_by_similarity(monkeypatch):
    """Q15: no keyword, so the similarity check decides -- with fixed vectors, no Azure call."""
    def fake_embeddings(texts):
        if len(texts) == 1:                     # the question
            return np.array([[1.0, 0.0]])
        return np.tile(np.array([0.0, 1.0]), (len(texts), 1))  # every example, orthogonal to it

    monkeypatch.setattr(topic, "embed_texts", fake_embeddings)
    monkeypatch.setattr(topic, "_reference_embeddings", None)  # drop any cached embeddings
    assert topic.check_topic("Write a poem about the monsoon.").verdict == topic.BLOCK


def test_one_year_answer_fails_format_for_a_comparison():
    assert check_format("In FY2026 OTIF was 93.4 per cent [2], which increased.", "compare_years").problems == \
        ["answer does not mention FY2025"]


def test_lookup_answer_is_not_held_to_the_comparison_rules():
    """Q5-Q10 are lookups: one document, one year, no change to describe."""
    decision = check_format("A purchase order of 15 crore needs the CPO's approval [1].", "lookup")
    assert decision.passed and decision.problems == []


def test_answer_must_cite_an_extract():
    assert check_format("A purchase order of 15 crore needs the CPO's approval.", "lookup").problems == \
        ["answer cites no extract, so no source is shown"]


def test_honest_cannot_answer_is_allowed():
    assert check_format("The extracts do not contain enough information to answer this question.", "lookup").passed


# --- the pause -----------------------------------------------------------------

def stub_nodes(monkeypatch, verdict):
    """Replace every working node with a stub; keep the real wiring, interrupt and checkpointer."""
    monkeypatch.setattr(graph_module, "input_guardrail_node", lambda s: {"input_allowed": True})
    monkeypatch.setattr(graph_module, "route_node", lambda s: {
        "intent": "lookup", "plan": [{"doc_type": "risk_register", "fiscal_year": "FY2026"}],
        "plan_reason": "stub", "attempts": 0, "rewritten_query": None})
    monkeypatch.setattr(graph_module, "retrieve_node", lambda s: {"candidate_chunks": {}, "attempts": 1})
    monkeypatch.setattr(graph_module, "rerank_node", lambda s: {"reranked_chunks": {}})
    monkeypatch.setattr(graph_module, "grade_node", lambda s: {
        "grader_sufficient": True, "grader_verdict": "sufficient", "grader_missing": "",
        "grader_better_query": None, "rewritten_query": None})
    monkeypatch.setattr(graph_module, "generate_node", lambda s: {"draft_answer": "draft"})
    monkeypatch.setattr(graph_module, "output_guardrail_node",
                        lambda s: {"grounding_verdict": verdict, "review_required": verdict != GROUNDED})


def test_unverified_answer_pauses_then_resumes(monkeypatch):
    stub_nodes(monkeypatch, NEEDS_REVIEW)
    graph = graph_module.build_graph()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke(create_initial_state("q"), thread)
    assert graph.get_state(thread).next == ("human_review",)       # paused
    graph.update_state(thread, {"review_decision": "approved", "review_note": "fixed"})
    assert graph.invoke(None, thread)["final_answer"] == "fixed"   # resumed with the reviewer's text


def test_grounded_answer_does_not_pause(monkeypatch):
    stub_nodes(monkeypatch, GROUNDED)
    graph = graph_module.build_graph()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    assert graph.invoke(create_initial_state("q"), thread)["final_answer"] == "draft"


# --- Q13-Q15 are refused before any search runs ---------------------------------

@pytest.mark.parametrize("question", [
    "Should we terminate Kestrel Semiconductors?",              # Q13: sourcing decision
    "What is the status of the supplier with PAN ABCDE1234F?",  # Q14: personal data
    "Write a poem about the monsoon.",                          # Q15: off topic
])
def test_refused_questions_never_reach_search(monkeypatch, question):
    def fake_embeddings(texts):
        if len(texts) == 1:
            return np.array([[1.0, 0.0]])
        return np.tile(np.array([0.0, 1.0]), (len(texts), 1))

    monkeypatch.setattr(topic, "embed_texts", fake_embeddings)
    monkeypatch.setattr(topic, "_reference_embeddings", None)
    monkeypatch.setattr(graph_module, "retrieve_node", lambda s: pytest.fail("a search ran"))
    monkeypatch.setattr(graph_module, "route_node", lambda s: pytest.fail("the router ran"))

    graph = graph_module.build_graph()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = graph.invoke(create_initial_state(question), thread)

    assert state["input_allowed"] is False          # refused at the door
    assert state["final_answer"]                    # with a polite message
    assert state["plan"] is None                    # nothing was planned
