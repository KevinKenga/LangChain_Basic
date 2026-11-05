"""state.py - the baton passed between nodes."""
import operator
from typing import Annotated, Any, TypedDict

class RAGState(TypedDict):
    # --- input ---
    question: str

    # --- input guardrail ---
    input_allowed: bool
    block_reason: str
    sensitive_intent: str            # "none" | "discount" | "refund" | "roadmap_commitment"

    # --- research loop ---
    candidates: Annotated[list[dict], operator.add]   # APPENDED across rounds
    search_log: Annotated[list[str], operator.add]    # every query the agent ran
    attempts: int                                      # research rounds so far
    context: list[dict]                                # after rerank
    grade: str                                         # "SUFFICIENT" | "INSUFFICIENT"
    grade_feedback: str                                # what is missing

    # --- answer ---
    draft_answer: str
    guardrail_report: dict[str, Any]
    needs_review: bool

    # --- human in the loop ---
    review: dict[str, str]           # {"decision": "approve"|"edit"|"reject", "note": ..., "edited": ...}
    final_answer: str

    # --- audit trail ---
    steps: Annotated[list[str], operator.add]
