"""
================================================================================
GRAPH PART 3 - THE NODES (what each step does)
================================================================================

A node is a function with one shape:

    def some_node(state) -> dict:
        return {"field_i_changed": new_value}

It reads the state, does ONE job, and returns only the fields it changed.
Nodes never call each other and never decide what runs next -- that lives in
build_graph.py. So a step can be swapped (Chroma -> Azure AI Search, local
cross-encoder -> semantic ranker) without touching its neighbours.

    input_guardrail   safety, then topic                 (Azure OpenAI only if needed)
    route             intent + at most 3 searches        (Azure OpenAI, gpt-4o-mini)
    retrieve          one filtered search per plan step  (Azure AI Search + Azure OpenAI)
    rerank            semantic ranker scores, 20 -> 5    (no new call -- scores came with search)
    grade             is the evidence enough?            (free check, then gpt-4o-mini)
    generate          write the cited answer             (Azure OpenAI, gpt-4o)
    output_guardrail  format, then grounding             (Azure OpenAI only if needed)
    human_review      apply the reviewer's decision
    finalise          approve an answer that needed no review
================================================================================
"""

import sys                                      # sys.path lets us import from the folder above
from pathlib import Path                        # Path builds file paths
from typing import Dict, List                   # type hints

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # deployment names
from azure_clients import openai_client         # Azure OpenAI, for writing the answer
from graph.grader import check_evidence         # is the evidence enough?
from graph.router import plan_question          # which documents to search
from graph.state import GraphState              # the shape of the state
from guardrails.factual import GROUNDED, NEEDS_REVIEW, check_grounding, collect_source_texts  # grounding check
from guardrails.format import check_format      # format check
from guardrails.safety import BLOCK, check_safety, refusal_message  # safety check
from guardrails.topic import REFUSAL_MESSAGE, check_topic  # topic check
from retrieval.rerank import rerank             # semantic-ranker cut, 20 -> 5
from retrieval.search import search_plan        # one filtered search per plan step


# ==============================================================================
# NODE 1 - INPUT GUARDRAIL
# ==============================================================================

def input_guardrail_node(state: GraphState) -> dict:
    """Refuse unsafe or off-topic questions before anything costs money."""
    safety = check_safety(state["question"])    # pattern check -- free, no Azure call
    if safety.verdict == BLOCK:                 # personal data or a sourcing decision?
        return {"input_allowed": False,         # stop here
                "input_block_reason": safety.reason,          # why, for the logs
                "final_answer": refusal_message(safety)}      # what the user sees

    topic = check_topic(state["question"])      # keyword check (free), then similarity (one embedding call)
    if topic.verdict == BLOCK:                  # off topic?
        return {"input_allowed": False,         # stop here
                "input_block_reason": topic.reason,           # why, for the logs
                "final_answer": REFUSAL_MESSAGE}              # what the user sees

    return {"input_allowed": True}              # passed both checks


# ==============================================================================
# NODE 2 - ROUTE (decision 1: which documents?)
# ==============================================================================

def route_node(state: GraphState) -> dict:
    """Plan the searches: an intent, at most 3 (doc_type, fiscal_year) pairs, and a reason."""
    plan = plan_question(state["question"])     # the model's plan, or the free keyword fallback
    return {"intent": plan.intent,              # compare_years / lookup / cross_document
            "plan": plan.searches,              # already validated: real pairs, no repeats, at most 3
            "plan_reason": plan.reason,         # one line, shown in the UI
            "attempts": 0,                      # no retrieval attempt yet
            "rewritten_query": None}            # nothing rewritten yet


# ==============================================================================
# NODES 3 AND 4 - RETRIEVE, THEN RERANK
# ==============================================================================
# Two nodes, not one, so the state holds BOTH the hybrid order and the semantic
# order -- and you can see exactly what the semantic ranker changed.
# ==============================================================================

def retrieve_node(state: GraphState) -> dict:
    """One filtered hybrid search per plan step, keyed by that step."""
    query = state.get("rewritten_query") or state["question"]  # the grader's rewrite on a retry, else the question
    return {"candidate_chunks": search_plan(query, state["plan"]),  # {"annual_review · FY2025": [...], ...}
            "search_query": query,              # what this attempt actually searched for
            "attempts": state.get("attempts", 0) + 1}  # count the attempt, so the loop can stop at 2


def rerank_node(state: GraphState) -> dict:
    """Keep each search's best 5 by semantic ranker score -- each search separately, so none dominates."""
    return {"reranked_chunks": {                # same keys, shorter lists
        key: rerank(candidates)                 # 20 -> 5 within this search
        for key, candidates in state["candidate_chunks"].items()
    }}


# ==============================================================================
# NODE 5 - GRADE (decision 2: is the evidence enough?)
# ==============================================================================

def grade_node(state: GraphState) -> dict:
    """Free empty-search check, then one model call. Records the verdict; build_graph.py routes on it."""
    verdict = check_evidence(state["question"], state["reranked_chunks"])  # the evidence, per search
    rewritten = None                            # no rewrite unless the grader asked for one
    if not verdict.sufficient:                  # not enough evidence?
        rewritten = verdict.better_query or state["question"]  # its suggestion, or the same question again
    return {"grader_sufficient": verdict.sufficient,           # True = generate now
            "grader_verdict": verdict.verdict,                 # sufficient / insufficient / unavailable
            "grader_missing": verdict.missing,                 # what it says is missing
            "grader_better_query": verdict.better_query,       # its suggested query
            "rewritten_query": rewritten}                      # what the retry will search for


# ==============================================================================
# NODE 6 - GENERATE
# ==============================================================================

GENERATION_PROMPT = """You answer questions about Nirmaan Motion Components Ltd's supply \
chain documents.

Use ONLY the numbered extracts below. If they do not contain enough information to answer,
say so plainly rather than filling the gap from general knowledge.

Cite every fact with the number of the extract it came from, in square brackets, like [2].
Every statement needs a citation.

When you state a figure, it must appear in the extracts. Do not calculate, estimate or round
beyond what is written.

Do not recommend whether to keep, drop, blacklist or replace a supplier. Describe what the
documents say.

Structure your answer as:
{structure}

=== EXTRACTS ===
{extracts}

QUESTION: {question}"""

# One answer shape per intent. A comparison is not a lookup, and a lookup is not
# a check of one document against another.
ANSWER_STRUCTURES = {
    "compare_years": "- what FY2025 said\n- what FY2026 said\n- what changed, or that nothing meaningful changed",
    "lookup": "- the direct answer first\n- the supporting detail from the extract(s)",
    "cross_document": "- what each document says, named by its title\n"
                      "- how they fit together, for example whether the data breaches the rule",
}


def format_extracts(results: Dict[str, List[Dict]]) -> str:
    """Number every extract [1], [2]... across all searches, naming its document title and year."""
    lines = []                                  # one block per search
    number = 0                                  # the citation number, continuous across searches
    for key, chunks in results.items():         # each planned search, in plan order
        if not chunks:                          # nothing retrieved for this search?
            lines.append(f"({key}: no relevant extracts found)")  # say so, so the model does not fill the gap itself
            continue                            # no numbers to hand out
        lines.append(f"=== {key} ===")          # a heading per search
        for chunk in chunks:                    # each kept chunk
            number += 1                         # the next citation number
            lines.append(f"[{number}] ({chunk['doc_title']}, {chunk['fiscal_year']}) {chunk['text']}")
    return "\n\n".join(lines)                   # blank line between blocks


def generate_node(state: GraphState) -> dict:
    """Write the cited answer with Azure OpenAI."""
    from openai import BadRequestError          # the error Azure raises when its content filter blocks a request

    reranked = state["reranked_chunks"]         # the 5 best chunks per search
    prompt = GENERATION_PROMPT.format(          # fill in the template
        structure=ANSWER_STRUCTURES.get(state.get("intent") or "lookup", ANSWER_STRUCTURES["lookup"]),
        extracts=format_extracts(reranked),     # every extract, numbered, with its document title
        question=state["question"],             # what was asked
    )

    try:
        response = openai_client().chat.completions.create(  # one call to Azure OpenAI
            model=config.GENERATION_DEPLOYMENT, # the capable deployment (gpt-4o)
            temperature=0.0,                    # same extracts -> same answer, so checks are reproducible
            messages=[{"role": "user", "content": prompt}],  # one instruction message
        )
        return {"draft_answer": response.choices[0].message.content.strip()}  # the answer text

    except BadRequestError as error:            # Azure-specific: every request passes through a CONTENT FILTER
        if "content_filter" not in str(error):  # some other bad request? that is a real bug -- let it surface
            raise
        # The filter blocked the prompt or the answer. We do not crash: the
        # format check will flag this draft, and a reviewer will see it.
        return {"draft_answer": "(The Azure OpenAI content filter blocked this answer.)"}


# ==============================================================================
# NODE 7 - OUTPUT GUARDRAIL
# ==============================================================================

def output_guardrail_node(state: GraphState) -> dict:
    """Format first (free), then grounding. Records a verdict; build_graph.py routes on it."""
    shape = check_format(state["draft_answer"], state.get("intent") or "lookup")  # rules depend on the intent
    if not shape.passed:                        # badly shaped?
        return {"grounding_verdict": NEEDS_REVIEW,  # send to a person...
                "grounding_score": 0.0,             # ...without spending a grounding call
                "unsupported_items": [f"format: {p}" for p in shape.problems],  # every broken rule
                "review_required": True}

    decision = check_grounding(                 # numbers (free), then claims (one Azure call) if needed
        state["draft_answer"],                  # the answer to check
        collect_source_texts(state["reranked_chunks"]),  # its sources, grouped by fiscal year
    )
    return {"grounding_verdict": decision.verdict,          # grounded / needs_review / ungrounded
            "grounding_score": decision.score,              # share of numbers traced
            "unsupported_items": decision.unsupported_items,  # what failed
            "review_required": decision.verdict != GROUNDED}  # anything but grounded needs a person


# ==============================================================================
# NODES 8 AND 9 - HUMAN REVIEW, FINALISE
# ==============================================================================

def human_review_node(state: GraphState) -> dict:
    """
    Runs AFTER a person has decided. The pause itself is not here -- LangGraph
    stops BEFORE this node (see build_graph.py) and waits for the decision.
    """
    decision = state.get("review_decision")     # written into the state by the reviewer
    if decision == "approved":                  # approved: show their correction, or the draft as written
        return {"final_answer": state.get("review_note") or state["draft_answer"]}
    return {"final_answer": (                   # rejected, or (unexpectedly) no decision: never show an unreviewed answer
        "I wasn't able to answer that reliably from the supply chain documents. "
        "Please try rephrasing, or refer to the documents directly."
    )}


def finalise_node(state: GraphState) -> dict:
    """The grounded path: the draft becomes the final answer. One exit point for every route."""
    return {"final_answer": state["draft_answer"]}  # copy the checked draft across
