"""
================================================================================
INPUT GUARDRAIL 2 - TOPIC (is this about the supply chain documents?)
================================================================================

Two checks, cheapest first:

    1. KEYWORDS     does the question use a supply chain word ("supplier",
                    "warehouse", "policy")?
                    -> allow straight away, with NO Azure call at all
    2. SIMILARITY   otherwise, embed the question with Azure OpenAI and compare
                    it with example questions we know are on topic
                    -> allow if it is close enough, block if not

Most real questions use a supply chain word, so most never reach the second
check.

HOW TO RUN
----------
    python guardrails/topic.py
================================================================================
"""

import re                                       # regular expressions for whole-word keyword matching
import sys                                      # sys.path lets us import from the folder above
from dataclasses import dataclass               # @dataclass writes __init__ for us
from pathlib import Path                        # Path builds file paths
from typing import List, Optional               # type hints

import numpy as np                              # fast maths on lists of numbers

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # threshold, deployment name
from azure_clients import openai_client         # Azure OpenAI, for embeddings

ALLOW = "allow"                                 # the question may continue
BLOCK = "block"                                 # the question stops here

DOMAIN_KEYWORDS = [                             # any one of these means "clearly about the documents"
    "supplier", "suppliers", "vendor", "vendors", "sourcing", "procurement",
    "purchase order", "purchase orders", "approval", "approver", "policy",
    "risk", "risks", "risk score", "mitigation", "single-source", "single sourced",
    "dual-sourcing", "dual sourcing", "scorecard", "band", "blacklist",
    "warehouse", "warehouses", "utilisation", "utilization", "logistics",
    "freight", "transport", "3pl", "control tower", "shipment", "dispatch",
    "otif", "inventory", "lead time", "lead times", "spend", "cost",
    "emissions", "headcount", "kpi", "annual review", "contract", "stock",
]

DOMAIN_REFERENCE_EXAMPLES = [                   # questions we KNOW are on topic; new questions are compared to these
    "How did customer OTIF change between the two financial years?",
    "What was the average import lead time in FY2026?",
    "Which suppliers are single-sourced and have a high risk score?",
    "Who must approve a purchase order of fifteen crore?",
    "What is the dual-sourcing threshold in the procurement policy?",
    "Which warehouse had the highest utilisation?",
    "How did freight and logistics cost change between the two years?",
    "What does the policy require for a band D supplier?",
    "Which critical suppliers have a CPO exception?",
    "How did procurement spend change year on year?",
    "What does the risk register say about mitigation plans?",
    "How did inventory days and year-end inventory value change?",
    "What are the payment terms in the procurement policy?",
    "Which transport modes does the logistics report describe?",
    "What does the scorecard band mean for a supplier?",
    "How did emissions and headcount change between the two years?",
]

REFUSAL_MESSAGE = (                             # what the user sees when the question is off topic
    "I can only answer questions about the supply chain documents -- the two annual "
    "reviews, the supplier risk register, the logistics and warehouse report, and the "
    "procurement policy. I can't help with other topics."
)


@dataclass
class TopicDecision:
    """The result of the topic check."""
    verdict: str                                # ALLOW or BLOCK
    check: str                                  # which check decided: "input", "keyword" or "similarity"
    reason: str                                 # a short explanation for the logs
    score: Optional[float] = None               # the similarity score, when the similarity check ran


def check_by_keywords(question: str) -> Optional[TopicDecision]:
    """ALLOW if a supply chain keyword appears as a whole word; None means 'cannot tell, ask the next check'."""
    lowered = question.lower()                  # compare in lower case so "Supplier" matches "supplier"
    matched = [k for k in DOMAIN_KEYWORDS        # keep every keyword...
               if re.search(rf"\b{re.escape(k)}\b", lowered)]  # ...found as a whole word ("risk" not in "brisk")
    if matched:                                 # at least one?
        return TopicDecision(ALLOW, "keyword", f"found domain terms: {', '.join(matched)}")
    return None                                 # no keyword -- let the similarity check decide


def embed_texts(texts: List[str]) -> np.ndarray:
    """Embed texts with Azure OpenAI and return them as a numpy table (one row per text)."""
    response = openai_client().embeddings.create(model=config.EMBEDDING_DEPLOYMENT, input=texts,
                                           dimensions=config.EMBEDDING_DIMENSIONS)  # one call
    return np.array([item.embedding for item in response.data])  # rows of EMBEDDING_DIMENSIONS numbers


def cosine_similarity(vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """How alike in direction the vector is to each row of the matrix: 1 = same meaning, 0 = unrelated."""
    vector = vector / (np.linalg.norm(vector) + 1e-10)                          # make its length 1 (1e-10 avoids /0)
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)  # make every row's length 1
    return matrix @ vector                      # @ multiplies: one similarity score per row


_reference_embeddings: Optional[np.ndarray] = None  # embeddings of the examples, computed once and remembered


def get_reference_embeddings() -> np.ndarray:
    """Embed the reference examples on first use, then reuse them."""
    global _reference_embeddings                # we are changing the variable defined above, not a local copy
    if _reference_embeddings is None:           # first time?
        _reference_embeddings = embed_texts(DOMAIN_REFERENCE_EXAMPLES)  # one Azure call for all 16 examples
    return _reference_embeddings                # every later call is free


def check_by_similarity(question: str) -> TopicDecision:
    """Compare the question's meaning with the on-topic examples."""
    scores = cosine_similarity(embed_texts([question])[0], get_reference_embeddings())  # one score per example
    best = float(np.max(scores))                # the closest example's score
    closest = DOMAIN_REFERENCE_EXAMPLES[int(np.argmax(scores))]  # which example that was, for the logs
    if best >= config.TOPIC_SIMILARITY_THRESHOLD:  # close enough?
        return TopicDecision(ALLOW, "similarity", f"close in meaning to: '{closest}'", best)
    return TopicDecision(BLOCK, "similarity", "not close to anything in the domain", best)


def check_topic(question: str) -> TopicDecision:
    """Empty -> block. Keyword -> allow (free). Otherwise -> similarity decides (one Azure call)."""
    if not question.strip():                    # nothing but spaces?
        return TopicDecision(BLOCK, "input", "question is empty")
    return check_by_keywords(question) or check_by_similarity(question)  # cheap check first


if __name__ == "__main__":                      # only when run directly
    for q in ["How did customer OTIF change?",  # keyword: allowed with no Azure call
              "What does the policy require for a band D supplier?",  # keyword: allowed
              "Write me a poem about the monsoon"]:  # off topic: should be blocked
        d = check_topic(q)                      # run the check
        print(f"  {d.verdict.upper():6} via {d.check:10} {q}")  # show the verdict and which check decided
