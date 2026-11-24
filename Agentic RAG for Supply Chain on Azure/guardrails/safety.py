"""
================================================================================
INPUT GUARDRAIL 1 - SAFETY (personal data, sourcing decisions)
================================================================================

Checks the question BEFORE anything else -- before any Azure service is called:

    1. Personal data        a PAN, Aadhaar number, email address or phone number
    2. Sourcing decisions   "should we terminate Kestrel Semiconductors?"

Personal data has no place in a question about supply chain documents. If it is
there, the user pasted it by mistake, and every later step (Azure OpenAI, the
logs) would receive a copy. Stopping it first means it goes nowhere.

A sourcing decision is ON topic -- "should we drop this supplier?" names a
supplier -- so the topic check would let it through. This check refuses it: the
documents describe risk, they do not decide what the company should do about a
supplier, and an answer that sounded like a decision could end a contract.

Both are simple patterns, so this runs in microseconds, costs nothing, and gives
the same answer every time.

HOW TO RUN
----------
    python guardrails/safety.py
================================================================================
"""

import re                                       # regular expressions: describe a text pattern, then search for it
from dataclasses import dataclass               # @dataclass writes __init__ for small data classes
from typing import List, Optional               # type hints

ALLOW = "allow"                                 # the question may continue
BLOCK = "block"                                 # the question stops here


@dataclass
class SafetyDecision:
    """The result of the safety check."""
    verdict: str                                # ALLOW or BLOCK
    check: str                                  # which check decided: "personal_data", "sourcing_decision" or "safety"
    reason: str                                 # for the logs -- names the KIND of data, never the data itself


# Each entry: (name for the log, pattern). \b is a word boundary, so a pattern
# never matches in the middle of a longer word or number.
PERSONAL_DATA_PATTERNS = [
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)),       # 5 letters, 4 digits, 1 letter
    ("Aadhaar number", re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")),  # 12 digits, never starting with 0 or 1
    ("email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),     # something@something.something
    ("phone number", re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b")),     # Indian mobile: 10 digits starting 6-9
]

# Phrases that ask us to decide what to do about a supplier. Words like
# "risk" or "score" are NOT here -- "what is the risk score of Kestrel?" is a
# perfectly good question about the register.
SOURCING_DECISION_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [     # compile each pattern once, case-insensitive
        r"\bshould (i|we) (terminate|drop|blacklist|replace|remove|de-?list|switch|fire)\b",  # "should we terminate"
        r"\bshould (i|we) (stop|exit|end) (buying|sourcing|working) (from|with)\b",           # "should we stop buying from"
        r"\b(terminate|drop|blacklist|replace|de-?list) (the |this |that )?(supplier|vendor)\b",  # "drop the supplier"
        r"\bwhich (supplier|vendor)s? should (we|i) (drop|terminate|blacklist|replace)\b",     # "which supplier should we drop"
        r"\b(is|are) \w+(\s\w+)? (a )?(good|bad|safe) (supplier|vendor) to (keep|use)\b",      # "is X a good supplier to keep"
    ]
]

PERSONAL_DATA_REFUSAL = (                       # what the user sees if personal data is found
    "Your question seems to contain personal information (such as a PAN, Aadhaar "
    "number, email or phone number). Please remove it and ask again -- it isn't "
    "needed to answer questions about the supply chain documents."
)

SOURCING_REFUSAL = (                            # what the user sees if a sourcing decision is requested
    "I can't recommend whether to keep, drop, blacklist or replace a supplier. I can "
    "tell you what the documents say -- for example a supplier's risk score, "
    "single-source status and mitigation, or what the procurement policy requires."
)


def check_personal_data(question: str) -> Optional[SafetyDecision]:
    """BLOCK if the question contains personal data; None if it does not."""
    for name, pattern in PERSONAL_DATA_PATTERNS:  # try each kind of personal data
        if pattern.search(question):              # found one?
            return SafetyDecision(BLOCK, "personal_data", f"question contains personal data ({name})")
    return None                                   # nothing found


def check_sourcing_decision(question: str) -> Optional[SafetyDecision]:
    """BLOCK if the question asks us to decide what to do about a supplier; None if it does not."""
    for pattern in SOURCING_DECISION_PATTERNS:  # try each sourcing-decision phrase
        if pattern.search(question):            # found one?
            return SafetyDecision(BLOCK, "sourcing_decision", "question asks for a sourcing decision")
    return None                                 # nothing found


def check_safety(question: str) -> SafetyDecision:
    """Run both checks. Personal data first: if both apply, that is what the user most needs to hear."""
    return (
        check_personal_data(question)           # a decision if personal data was found, else None...
        or check_sourcing_decision(question)    # ...then a decision if a sourcing decision was asked for, else None...
        or SafetyDecision(ALLOW, "safety", "no personal data or sourcing decision found")  # ...else allow
    )


def refusal_message(decision: SafetyDecision) -> str:
    """The message the user sees for a blocked question."""
    return PERSONAL_DATA_REFUSAL if decision.check == "personal_data" else SOURCING_REFUSAL


if __name__ == "__main__":                      # only when run directly
    for q in [                                  # a few examples, allowed and blocked
        "How did customer OTIF change between the two years?",
        "Should we terminate Kestrel Semiconductors?",
        "Should we blacklist the supplier with the highest risk score?",
        "My PAN is ABCDE1234F, what is the risk score of Kestrel?",
    ]:
        d = check_safety(q)                     # run the check
        print(f"  {d.verdict.upper():6} {q}\n         {d.reason}")  # show the verdict and the reason
