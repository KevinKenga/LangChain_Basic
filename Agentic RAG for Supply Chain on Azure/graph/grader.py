"""
================================================================================
GRAPH PART 2b - THE GRADER (is the evidence enough to answer?)
================================================================================

DECISION 2 OF THE AGENT
-----------------------
After the searches come back and the semantic ranker has cut them down, check
whether the text found is enough to answer the question. If it is not, rewrite
the search query and search again -- once. Then write the answer.

TWO CHECKS, CHEAPEST FIRST
--------------------------
    1. EMPTY SEARCH   free, instant. Did any planned search return nothing?
                      If one did, the evidence is already incomplete and no
                      model call is needed to say so.
    2. MODEL VERDICT  one gpt-4o-mini call returns JSON:
                          {"sufficient": true|false,
                           "missing": "...",
                           "better_query": "..."}

WHAT HAPPENS IF THE GRADER CALL FAILS
-------------------------------------
The verdict becomes sufficient=True and the pipeline goes on to generate. That
is deliberate, and it is safe here because the grader is not the last line of
defence:

    - the generation prompt may use only the numbered extracts, and must say
      plainly when they are not enough;
    - the output guardrails then check the answer: format rules for the intent,
      and every figure traced to the right year's chunks;
    - anything that cannot be verified PAUSES for a person before it is shown.

So a failed grader call costs at most one extra generation call. Treating it as
"insufficient" instead would spend the retry on a query nobody improved, and
then generate anyway -- the same answer, one search later.

HOW TO RUN
----------
    python graph/grader.py        (the empty-search check only -- no Azure call)
================================================================================
"""

import sys                                      # sys.path lets us import from the folder above
from dataclasses import dataclass               # @dataclass writes __init__ for small data classes
from pathlib import Path                        # Path builds file paths
from typing import Dict, List, Optional         # type hints

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # deployment name
from graph.router import parse_json_object      # the same tolerant JSON reader the router uses

SUFFICIENT = "sufficient"                       # the evidence is enough
INSUFFICIENT = "insufficient"                   # it is not
UNAVAILABLE = "unavailable"                     # the grader could not judge -- treated as sufficient

EMPTY_SEARCH = "empty_search"                   # the free check decided
MODEL = "model"                                 # the model call decided


@dataclass
class GraderVerdict:
    """The grader's decision about one round of evidence."""
    sufficient: bool                            # True = generate now
    missing: str = ""                           # what the grader says is missing
    better_query: Optional[str] = None          # a search query it suggests instead
    verdict: str = SUFFICIENT                   # SUFFICIENT, INSUFFICIENT or UNAVAILABLE
    source: str = MODEL                         # EMPTY_SEARCH or MODEL


GRADER_PROMPT = """You check whether retrieved extracts are enough to answer a question.

Answer with JSON only, in exactly this shape:
{{"sufficient": true|false, "missing": "what is missing, or empty", "better_query": "a better search query, or empty"}}

Say sufficient=true only if the extracts contain the facts the question asks for.
If they do not, say what is missing and suggest ONE search query that would find it.

QUESTION: {question}

EXTRACTS:
{extracts}"""


def format_extracts(results: Dict[str, List[Dict]]) -> str:
    """Lay the extracts out under one heading per search, so the grader can see which search found what."""
    blocks = []                                 # one block per search
    for key, chunks in results.items():         # each planned search
        body = "\n\n".join(chunk["text"] for chunk in chunks) or "(no extracts)"  # that search's text
        blocks.append(f"=== {key} ===\n{body}")  # a heading, then the text
    return "\n\n".join(blocks)                  # blank line between searches


def empty_searches(results: Dict[str, List[Dict]]) -> List[str]:
    """The keys of every planned search that came back with nothing."""
    return [key for key, chunks in results.items() if not chunks]  # an empty list is the signal


def model_verdict(question: str, results: Dict[str, List[Dict]]) -> GraderVerdict:
    """Ask the fast deployment whether the evidence is enough."""
    from azure_clients import openai_client     # imported here, so importing this file needs no Azure settings

    response = openai_client().chat.completions.create(  # one call to Azure OpenAI
        model=config.GRADER_DEPLOYMENT,         # the cheap "fast" deployment
        temperature=0,                          # same evidence -> same verdict, every time
        max_completion_tokens=800,              # a small JSON object; room is left for a reasoning model's hidden work
        messages=[{"role": "user",              # a single instruction message
                   "content": GRADER_PROMPT.format(question=question, extracts=format_extracts(results))}],
    )
    parsed = parse_json_object(response.choices[0].message.content or "")  # the JSON object, if there is one
    if parsed is None or not isinstance(parsed.get("sufficient"), bool):   # no usable verdict?
        raise ValueError("grader reply was not usable JSON")               # the caller treats it as unavailable

    sufficient = parsed["sufficient"]           # the model's answer
    return GraderVerdict(
        sufficient=sufficient,
        missing=str(parsed.get("missing") or "").strip(),
        better_query=(str(parsed.get("better_query") or "").strip() or None),
        verdict=SUFFICIENT if sufficient else INSUFFICIENT,
        source=MODEL,
    )


def check_evidence(question: str, results: Dict[str, List[Dict]]) -> GraderVerdict:
    """Free empty-search check first, then one model call. A failed call counts as sufficient."""
    empty = empty_searches(results)             # did any planned search return nothing?
    if empty:                                   # yes -- no model call needed to know the evidence is incomplete
        return GraderVerdict(
            sufficient=False,
            missing="no chunks returned for " + ", ".join(empty),
            verdict=INSUFFICIENT,
            source=EMPTY_SEARCH,
        )

    try:
        return model_verdict(question, results)  # one gpt-4o-mini call
    except Exception:                            # no key, network, quota, content filter, bad JSON...
        # Proceed rather than loop: the output guardrails and the human review
        # still catch an answer the extracts do not support (see the module
        # docstring for the full argument).
        return GraderVerdict(sufficient=True, missing="", verdict=UNAVAILABLE, source=MODEL)


if __name__ == "__main__":                      # only when run directly
    EMPTY = {"annual_review · FY2025": [], "annual_review · FY2026": [{"text": "OTIF was 91.2 per cent."}]}
    verdict = check_evidence("How did OTIF change?", EMPTY)  # the free check decides: one search was empty
    print(f"  {verdict.verdict:13} {verdict.missing}")       # no Azure call was made
