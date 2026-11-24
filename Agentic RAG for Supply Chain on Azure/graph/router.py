"""
================================================================================
GRAPH PART 2a - THE ROUTER (which documents should this question search?)
================================================================================

DECISION 1 OF THE AGENT
-----------------------
Read the question and decide which of the five documents to search. A question
about a policy rule should search only the policy. A question that compares two
years should search both annual reviews. A question that checks data against a
rule should search two different documents.

TWO STEPS, IN THIS ORDER
------------------------
    1. MODEL PLAN     one gpt-4o-mini call returns JSON:
                          {"intent": ..., "searches": [...], "reason": "..."}
    2. VALIDATION     plain Python checks the plan before anything is searched

WHY VALIDATE WHAT THE MODEL WROTE
---------------------------------
The model is a language model, not a schema. It can return a doc_type that does
not exist, the same search twice, four searches when three are allowed, or
intent "compare_years" with only one year in the plan. None of that should
reach Azure AI Search, because a search for a pair that does not exist returns
nothing and looks like "the documents don't say" -- a wrong answer with no
error. So the plan is cleaned up here, in code we can read and test:

    drop pairs that do not exist     config.VALID_PAIRS is the only truth
    remove repeats                   the same search twice wastes a call
    cap at MAX_SEARCHES              three searches is the budget
    compare_years gets both reviews  a comparison with one year is not a comparison

THE FREE FALLBACK
-----------------
If the model call fails (no key, network, quota, content filter) or its plan is
unusable, a keyword router takes over. It costs nothing, needs no Azure call,
and always returns a valid plan. That is what makes the pipeline work offline
and what the tests exercise with the OpenAI key removed.

HOW TO RUN
----------
    python graph/router.py        (the fallback only -- no Azure call)
================================================================================
"""

import json                                     # the model replies with JSON; we parse it here
import re                                       # whole-word keyword matching for the fallback
import sys                                      # sys.path lets us import from the folder above
from dataclasses import dataclass, field        # small data class for the plan
from pathlib import Path                        # Path builds file paths
from typing import Dict, List, Optional         # type hints

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # valid pairs, search cap, deployment name

COMPARE_YEARS = "compare_years"                 # two years of the same document
LOOKUP = "lookup"                               # one document answers it
CROSS_DOCUMENT = "cross_document"               # two documents together
INTENTS = (COMPARE_YEARS, LOOKUP, CROSS_DOCUMENT)

MODEL = "model"                                 # the plan came from the model
FALLBACK = "fallback"                           # the plan came from the keyword router


@dataclass
class RouterPlan:
    """The router's decision: an intent, at most three searches, and a one-line reason."""
    intent: str                                 # COMPARE_YEARS, LOOKUP or CROSS_DOCUMENT
    searches: List[Dict[str, str]] = field(default_factory=list)  # [{"doc_type": ..., "fiscal_year": ...}, ...]
    reason: str = ""                            # one line, for the UI and the logs
    source: str = MODEL                         # MODEL or FALLBACK


# ==============================================================================
# SECTION 1 - THE MODEL PLAN
# ==============================================================================

ROUTER_PROMPT = """You route questions for a supply chain team. Choose which documents to search.

The only documents that exist (doc_type, fiscal_year):
{documents}

Intents:
- compare_years: the question compares two years. Always search BOTH annual reviews.
- lookup: one document answers it.
- cross_document: two documents are needed together (for example data from the
  risk register checked against a rule in the procurement policy).

Rules:
- At most {max_searches} searches.
- Use only the (doc_type, fiscal_year) pairs listed above. Never invent one.
- Do not repeat a search.

Reply with JSON only, in exactly this shape:
{{"intent": "compare_years|lookup|cross_document",
  "searches": [{{"doc_type": "...", "fiscal_year": "..."}}],
  "reason": "one short line"}}

QUESTION: {question}"""


def documents_block() -> str:
    """The five documents, one per line, for the prompt."""
    return "\n".join(                            # one line per document
        f"- {doc['doc_type']}, {doc['fiscal_year']}: {doc['doc_title']}"  # e.g. "- annual_review, FY2025: Annual Review FY2025"
        for doc in config.DOCUMENTS
    )


def parse_json_object(reply: str) -> Optional[Dict]:
    """Pull the first {...} object out of a model reply, or None if there is not one."""
    start, end = reply.find("{"), reply.rfind("}")  # the outermost braces
    if start == -1 or end <= start:             # no object at all?
        return None                             # unusable
    try:
        parsed = json.loads(reply[start:end + 1])  # the text between them, as JSON
    except json.JSONDecodeError:                # not valid JSON (a stray comma, a comment...)
        return None                             # unusable
    return parsed if isinstance(parsed, dict) else None  # a JSON object, not a list or a number


def model_plan(question: str) -> Optional[RouterPlan]:
    """Ask the fast deployment for a plan. Returns None if the reply is unusable."""
    from azure_clients import openai_client     # imported here, so importing this file needs no Azure settings

    response = openai_client().chat.completions.create(  # one call to Azure OpenAI
        model=config.ROUTER_DEPLOYMENT,         # the cheap "fast" deployment
        temperature=0,                          # same question -> same plan, every time
        max_completion_tokens=800,              # a small JSON object; room is left for a reasoning model's hidden work
        messages=[{"role": "user",              # a single instruction message
                   "content": ROUTER_PROMPT.format(documents=documents_block(),
                                                   max_searches=config.MAX_SEARCHES,
                                                   question=question)}],
    )
    parsed = parse_json_object(response.choices[0].message.content or "")  # the JSON object, if there is one
    if parsed is None:                          # no usable JSON?
        return None                             # the caller falls back
    return validate_plan(parsed.get("intent"), parsed.get("searches"), parsed.get("reason"))


# ==============================================================================
# SECTION 2 - VALIDATION IN PLAIN PYTHON
# ==============================================================================

def validate_plan(intent, searches, reason) -> Optional[RouterPlan]:
    """
    Clean up a plan, or return None if nothing usable is left.

    Drop pairs that do not exist, remove repeats, cap at MAX_SEARCHES, and make
    compare_years include both annual reviews.
    """
    if intent not in INTENTS:                   # an intent we do not know?
        return None                             # unusable -- the caller falls back

    cleaned: List[tuple] = []                   # (doc_type, fiscal_year) pairs, in order, without repeats
    for step in searches or []:                 # each search the model proposed
        if not isinstance(step, dict):          # not even an object?
            continue                            # drop it
        pair = (str(step.get("doc_type", "")).strip(), str(step.get("fiscal_year", "")).strip())
        if pair not in config.VALID_PAIRS:      # a document that does not exist?
            continue                            # drop it -- searching it would return nothing
        if pair in cleaned:                     # already planned?
            continue                            # drop the repeat
        cleaned.append(pair)                    # keep it

    if intent == COMPARE_YEARS:                 # a comparison needs both sides
        required = [("annual_review", "FY2025"), ("annual_review", "FY2026")]  # both reviews, in year order
        cleaned = required + [pair for pair in cleaned if pair not in required]  # both first, then the rest

    cleaned = cleaned[:config.MAX_SEARCHES]     # never more than the budget
    if not cleaned:                             # nothing survived?
        return None                             # unusable -- the caller falls back

    return RouterPlan(                          # a plan we can trust
        intent=intent,
        searches=[{"doc_type": doc_type, "fiscal_year": year} for doc_type, year in cleaned],
        reason=(reason or "").strip() or "no reason given",
        source=MODEL,
    )


# ==============================================================================
# SECTION 3 - THE FREE KEYWORD FALLBACK
# ==============================================================================
# Used when the model call fails or returns an unusable plan. No Azure call, no
# cost, and it always returns a valid plan.
# ==============================================================================

COMPARE_WORDS = re.compile(                     # signs the question compares two years
    r"\b(change[ds]?|changing|compare|comparison|versus|vs|difference|grew|grow|"
    r"increased|decreased|rose|fell|declin(e|ed)|higher|lower)\b",
    re.IGNORECASE,
)

REVISION_WORDS = re.compile(                    # a policy revision question is a lookup, not a comparison
    r"\b(previous version|revision history|old threshold|earlier version|version)\b",
    re.IGNORECASE,
)

# Any one of these words points at a document. Whole words only, so "risk" does
# not match inside "brisk".
DOC_TYPE_KEYWORDS = {
    "procurement_policy": [
        "policy", "approval", "approve", "approver", "purchase order", "bidding", "tender",
        "onboarding", "dual-sourcing", "dual sourcing", "scorecard band", "band a", "band b",
        "band c", "band d", "payment terms", "threshold", "revision", "delegation", "authority",
    ],
    "risk_register": [
        "supplier", "suppliers", "risk score", "single-source", "single sourced", "single-sourced",
        "critical supplier", "mitigation", "cpo exception", "scorecard", "blacklist", "vendor",
    ],
    "logistics_report": [
        "warehouse", "warehouses", "utilisation", "utilization", "freight", "3pl", "transport",
        "control tower", "logistics", "dispatch", "inbound", "outbound", "shipment",
    ],
    "annual_review": [
        "otif", "inventory", "spend", "lead time", "lead times", "emissions", "headcount",
        "people", "kpi", "annual review", "year-end", "service level", "cost per",
    ],
}

DOC_TYPE_ORDER = ["annual_review", "risk_register", "logistics_report", "procurement_policy"]  # a stable plan order


def matched_doc_types(question: str) -> List[str]:
    """Which documents the question's words point at, in a stable order."""
    lowered = question.lower()                  # compare in lower case so "Supplier" matches "supplier"
    found = []                                  # documents whose keywords appear
    for doc_type in DOC_TYPE_ORDER:             # a fixed order, so the same question always plans the same way
        words = DOC_TYPE_KEYWORDS[doc_type]     # this document's keywords
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):  # any one, as a whole word?
            found.append(doc_type)              # keep the document
    return found


def keyword_plan(question: str) -> RouterPlan:
    """A plan built from keywords alone -- free, offline, and always valid."""
    if COMPARE_WORDS.search(question) and not REVISION_WORDS.search(question):  # a comparison?
        return RouterPlan(                      # both annual reviews, always
            intent=COMPARE_YEARS,
            searches=[{"doc_type": "annual_review", "fiscal_year": "FY2025"},
                      {"doc_type": "annual_review", "fiscal_year": "FY2026"}],
            reason="keyword fallback: the question compares two years",
            source=FALLBACK,
        )

    doc_types = matched_doc_types(question)     # which documents the words point at
    if not doc_types:                           # nothing recognised?
        doc_types = ["annual_review"]           # the annual review is the general-purpose document
    doc_types = doc_types[:config.MAX_SEARCHES]  # never more than the budget

    return RouterPlan(                          # one search per document, latest year
        intent=CROSS_DOCUMENT if len(doc_types) > 1 else LOOKUP,  # two documents together, or one lookup
        searches=[{"doc_type": doc_type, "fiscal_year": "FY2026"} for doc_type in doc_types],
        reason="keyword fallback: matched " + ", ".join(doc_types),
        source=FALLBACK,
    )


# ==============================================================================
# SECTION 4 - BOTH TOGETHER
# ==============================================================================

def plan_question(question: str) -> RouterPlan:
    """Try the model, then fall back to keywords. Always returns a valid plan."""
    try:
        plan = model_plan(question)             # one gpt-4o-mini call
    except Exception:                           # no key, network, quota, content filter, bad JSON...
        plan = None                             # fall through to the free router
    return plan or keyword_plan(question)       # the model's plan if usable, otherwise keywords


if __name__ == "__main__":                      # only when run directly
    for q in [                                  # the fallback only: no Azure call is made here
        "How did customer OTIF change between FY2025 and FY2026?",
        "Who must approve a purchase order of 15 crore?",
        "Which single-sourced suppliers breach the dual-sourcing rule in the procurement policy?",
        "Write a poem about the monsoon.",
    ]:
        plan = keyword_plan(q)                  # the free router
        print(f"  {plan.intent:14} {plan.searches}\n                 {q}")  # what it planned, and why
