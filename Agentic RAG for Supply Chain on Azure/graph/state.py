"""
================================================================================
GRAPH PART 1 - THE STATE (everything that flows through the pipeline)
================================================================================

LangGraph passes ONE dictionary from step to step. Each step (node) reads what
it needs from it and returns only the fields it changed. This file lists every
field, in the order they get filled in -- reading it top to bottom is like
watching a question travel through the pipeline.

The two decisions the agent makes on its own are both visible here:

    plan      the router's list of (doc_type, fiscal_year) searches
    attempts  how many retrieval attempts have run, so the loop can stop at 2

HOW TO RUN
----------
    python graph/state.py
================================================================================
"""

from typing import Dict, List, Optional, TypedDict  # TypedDict: a dictionary with named, typed keys


class GraphState(TypedDict):
    """Every field the pipeline can hold."""
    # --- filled in by the caller ---
    question: str                               # what the user asked

    # --- input guardrails (safety, then topic) ---
    input_allowed: bool                         # False = the question was refused
    input_block_reason: Optional[str]           # why it was refused (for the logs)

    # --- the router's decision ---
    intent: Optional[str]                       # "compare_years", "lookup" or "cross_document"
    plan: Optional[List[Dict]]                  # [{"doc_type": ..., "fiscal_year": ...}, ...] -- at most 3
    plan_reason: Optional[str]                  # the router's one-line reason (or the fallback's)

    # --- retrieval (Azure AI Search), keyed by search ---
    search_query: Optional[str]                 # the query the last retrieval actually used
    attempts: int                               # retrieval attempts so far: 0, then 1, then 2
    candidate_chunks: Optional[Dict[str, List[Dict]]]  # ~20 per search, in hybrid-search order
    reranked_chunks: Optional[Dict[str, List[Dict]]]   # 5 per search, in semantic-ranker order

    # --- the grader's verdict ---
    grader_sufficient: Optional[bool]           # True = the evidence is enough to answer
    grader_verdict: Optional[str]               # "sufficient", "insufficient" or "unavailable"
    grader_missing: Optional[str]               # what the grader says is missing
    grader_better_query: Optional[str]          # the grader's suggested search query
    rewritten_query: Optional[str]              # the query the retry will use

    # --- generation (Azure OpenAI) ---
    draft_answer: Optional[str]                 # the model's answer, before any check

    # --- output guardrails (format, then grounding) ---
    grounding_verdict: Optional[str]            # "grounded", "needs_review" or "ungrounded"
    grounding_score: Optional[float]            # share of numbers that traced back
    unsupported_items: Optional[List[str]]      # exactly what failed -- shown to the reviewer
    review_required: bool                       # True = the graph will pause for a person

    # --- human review ---
    review_decision: Optional[str]              # "approved" or "rejected", written in by the reviewer
    review_note: Optional[str]                  # the reviewer's corrected answer, if they wrote one

    # --- the result ---
    final_answer: Optional[str]                 # what the user actually sees


def create_initial_state(question: str) -> GraphState:
    """A fresh state. Every field is set (to None if empty), so reading one never raises KeyError."""
    return GraphState(
        question=question,                      # from the caller
        input_allowed=True,                     # allowed until a guardrail says otherwise
        input_block_reason=None,                # nothing blocked yet
        intent=None,                            # the router has not run yet
        plan=None,                              # no searches planned yet
        plan_reason=None,                       # no reason yet
        search_query=None,                      # nothing searched yet
        attempts=0,                             # no retrieval attempt yet
        candidate_chunks=None,                  # nothing retrieved yet
        reranked_chunks=None,                   # nothing reranked yet
        grader_sufficient=None,                 # nothing graded yet
        grader_verdict=None,                    # nothing graded yet
        grader_missing=None,                    # nothing graded yet
        grader_better_query=None,               # nothing graded yet
        rewritten_query=None,                   # nothing rewritten yet
        draft_answer=None,                      # nothing generated yet
        grounding_verdict=None,                 # nothing checked yet
        grounding_score=None,                   # nothing measured yet
        unsupported_items=None,                 # nothing flagged yet
        review_required=False,                  # no review needed until a check says so
        review_decision=None,                   # no reviewer yet
        review_note=None,                       # no correction yet
        final_answer=None,                      # no answer yet
    )


if __name__ == "__main__":                      # only when run directly
    for key, value in create_initial_state("How did customer OTIF change?").items():  # a fresh state
        print(f"  {key:<20} {value!r}")         # !r shows None and strings clearly
