"""
================================================================================
OUTPUT GUARDRAIL 1 - FORMAT (is the answer shaped like the intent asked for?)
================================================================================

Checks the SHAPE of the draft answer before the grounding check reads it:

    1. sensible length    not empty, not a runaway essay
    2. no advice          no "we recommend dropping this supplier"
    3. cites an extract   at least one [n], so the reader can see where it came from
    4. both years         FY2025 and FY2026 are both mentioned   (compare_years only)
    5. says what changed  or says plainly that nothing did       (compare_years only)

WHY RULES 4 AND 5 DEPEND ON THE INTENT
--------------------------------------
They are comparison rules. "Who must approve a purchase order of 15 crore?" is a
lookup in the procurement policy: its answer names one document and one year,
and it has no change to describe. Applying the comparison rules to it would
flag a perfectly good answer as badly shaped, send it to a person, and make
every lookup look unreliable. So they run only when the router said
compare_years.

An answer can be perfectly grounded and still useless here -- for example, it
describes FY2026 accurately and never mentions FY2025. That is not a comparison.

It is free (pure pattern matching), so it runs before grounding: a badly shaped
answer goes to review without spending an Azure call on it.

Each rule is a small function that returns a problem in plain English, or None.
ALL rules run, so the reviewer sees every problem, not just the first.

HOW TO RUN
----------
    python guardrails/format.py
================================================================================
"""

import re                                       # regular expressions
import sys                                      # sys.path lets us import from the folder above
from dataclasses import dataclass, field        # small data class for the result
from pathlib import Path                        # Path builds file paths
from typing import Callable, List, Optional     # type hints

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # the fiscal years
from guardrails.factual import year_labels      # reuse the year-label patterns, so both checks agree

MIN_ANSWER_LENGTH = 40                          # characters: shorter is not a real answer
MAX_ANSWER_LENGTH = 6000                        # characters: longer has usually drifted from the extracts

ADVICE_PHRASES = re.compile(                    # signs the model gave advice despite being told not to
    r"\b(we|i) (would )?(recommend|suggest|advise) (dropping|terminating|blacklisting|replacing|keeping)|"
    r"\b(should|must) (drop|terminate|blacklist|replace|de-?list)\b",
    re.IGNORECASE,
)

CITATION_MARKER = re.compile(r"\[\d{1,2}\]")    # a citation such as [1] or [12]

CHANGE_WORDS = re.compile(                      # signs the answer addresses change -- or says there was none
    r"\b(chang|increas|decreas|rose|fell|grew|declin|improv|differ|"
    r"same|similar|unchanged|consistent|no meaningful|remained)",
    re.IGNORECASE,
)

CANNOT_ANSWER = re.compile(                     # an honest "the documents don't say" -- must not be punished
    r"\b(do not|does not|don't|doesn't) (contain|provide|include|mention)|"
    r"\bnot enough information\b|\bno relevant extracts\b",
    re.IGNORECASE,
)


def names_year(text: str, fiscal_year: str) -> bool:
    """True if the text names this fiscal year in any of its usual forms."""
    return any(re.search(p, text, re.IGNORECASE) for p in year_labels(fiscal_year))


def sensible_length(text: str) -> Optional[str]:
    """Rule 1: not too short, not too long."""
    if len(text.strip()) < MIN_ANSWER_LENGTH:   # too short?
        return "answer is too short to be a real answer"
    if len(text) > MAX_ANSWER_LENGTH:           # too long?
        return f"answer is longer than {MAX_ANSWER_LENGTH} characters"
    return None                                 # fine


def no_advice(text: str) -> Optional[str]:
    """Rule 2: no sourcing recommendation."""
    return "answer recommends a sourcing decision" if ADVICE_PHRASES.search(text) else None


def cites_an_extract(text: str) -> Optional[str]:
    """Rule 3: at least one [n] citation (skipped for an honest 'cannot answer')."""
    if CANNOT_ANSWER.search(text):              # the model said the documents don't cover it
        return None                             # there may be nothing to cite
    return None if CITATION_MARKER.search(text) else "answer cites no extract, so no source is shown"


def covers_both_years(text: str) -> Optional[str]:
    """Rule 4 (compare_years only): both years are mentioned (skipped for an honest 'cannot answer')."""
    if CANNOT_ANSWER.search(text):              # the model said the documents don't cover it
        return None                             # that is allowed
    missing = [y for y in config.FISCAL_YEARS if not names_year(text, y)]  # years never mentioned
    return f"answer does not mention {' or '.join(missing)}" if missing else None


def says_what_changed(text: str) -> Optional[str]:
    """Rule 5 (compare_years only): the answer says what changed, or that nothing did."""
    if CANNOT_ANSWER.search(text):              # honest "cannot answer" is allowed
        return None
    return None if CHANGE_WORDS.search(text) else "answer does not say what changed, or that nothing did"


ALWAYS_RULES: List[Callable[[str], Optional[str]]] = [  # every rule, whatever the intent
    sensible_length,
    no_advice,
    cites_an_extract,
]

INTENT_RULES: dict = {                          # extra rules, by intent
    "compare_years": [covers_both_years, says_what_changed],  # a comparison must compare
}


@dataclass
class FormatDecision:
    """The result of the format check."""
    passed: bool                                # True if every rule held
    problems: List[str] = field(default_factory=list)  # one sentence per broken rule


def check_format(answer: str, intent: str = "lookup") -> FormatDecision:
    """Run every rule for this intent and collect every problem."""
    rules = ALWAYS_RULES + INTENT_RULES.get(intent, [])  # the comparison rules only when comparing
    problems = [problem for rule in rules if (problem := rule(answer))]  # := saves each result while testing it
    return FormatDecision(passed=not problems, problems=problems)       # passed only if the list is empty


if __name__ == "__main__":                      # only when run directly
    for answer, intent in [                     # a few examples
        ("In FY2025 OTIF was 91.2 per cent [1]. In FY2026 it was 93.4 per cent [2], an increase.", "compare_years"),
        ("In FY2026 OTIF was 93.4 per cent [2], which increased from the prior year.", "compare_years"),
        ("A purchase order of 15 crore needs the CPO's approval [1].", "lookup"),
        ("The extracts do not contain enough information to answer this question.", "lookup"),
    ]:
        d = check_format(answer, intent)        # run the rules for this intent
        print(f"  {'PASS' if d.passed else 'FAIL'}  {intent:14} {answer[:50]}  {d.problems}")  # verdict and problems
