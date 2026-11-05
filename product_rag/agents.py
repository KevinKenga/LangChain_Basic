"""agents.py - one function per node: state in, partial update out."""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
import config
from state import RAGState
from tools import search_product_docs
from rerank import rerank
from guardrails import check_input, mask_pii, grounding_score

# ---------------------------------------------------------------- 1. input guardrail
def input_guardrail(state: RAGState) -> dict:
    v = check_input(state["question"])
    if not v.get("allowed"):
        return {"input_allowed": False, "block_reason": v.get("reason", ""),
                "final_answer": "Sorry, I can only answer questions about FlowDesk.",
                "steps": [f"INPUT_GUARDRAIL: blocked ({v.get('reason')})"]}
    return {"input_allowed": True, "sensitive_intent": v.get("sensitive_intent", "none"),
            "steps": [f"INPUT_GUARDRAIL: allowed, intent={v.get('sensitive_intent')}"]}

# ---------------------------------------------------------------- 2. research agent (ReAct)
RESEARCH_PROMPT = """You are a research agent for FlowDesk's internal documents.
Plan the searches needed to answer the question. Call search_product_docs one or more
times with short, specific queries and the right doc_type. Questions that combine a
target with an actual, or a request with a roadmap date, need searches in more than one
document. Stop calling tools when you have searched everything needed."""

def research_agent(state: RAGState) -> dict:
    llm = ChatOpenAI(model=config.AGENT_MODEL, temperature=0).bind_tools([search_product_docs])
    task = f"Question: {state['question']}"
    if state.get("grade_feedback"):
        already = "\n".join(f"- {q}" for q in state.get("search_log", [])) or "- (none)"
        task += (f"\n\nThis is a RETRY. A grader said the evidence found so far is missing: "
                 f"{state['grade_feedback']}\n"
                 f"Queries already run (do NOT repeat them):\n{already}\n"
                 f"Search for the missing information with new wording and/or a different doc_type.")
    messages = [SystemMessage(RESEARCH_PROMPT), HumanMessage(task)]

    found, log = [], []
    for _ in range(config.MAX_TOOL_CALLS):        # safety limit, as in Assignment 1
        response = llm.invoke(messages)
        if not response.tool_calls:
            break
        messages.append(response)
        for call in response.tool_calls:
            chunks = search_product_docs.invoke(call["args"])
            found += chunks
            log.append(f"{call['args'].get('doc_type') or 'all'}: {call['args']['query']}")
            # send back short previews, not full chunks, to keep the loop cheap
            preview = [{"doc_type": c["doc_type"], "page": c["page"], "text": c["text"][:200]}
                       for c in chunks]
            messages.append(ToolMessage(json.dumps(preview), tool_call_id=call["id"]))

    attempts = state.get("attempts", 0) + 1
    return {"candidates": found, "search_log": log, "attempts": attempts,
            "steps": [f"RESEARCH_AGENT round {attempts}: {len(log)} searches, {len(found)} chunks"]}

# ---------------------------------------------------------------- 3. rerank
def rerank_node(state: RAGState) -> dict:
    top = rerank(state["question"], state["candidates"])
    return {"context": top,
            "steps": [f"RERANK: {len(state['candidates'])} candidates -> {len(top)} kept"]}

# ---------------------------------------------------------------- 4. grade context
GRADE_PROMPT = """Decide whether the CONTEXT contains enough information to fully answer
the QUESTION. Return JSON only: {"grade": "SUFFICIENT"|"INSUFFICIENT", "missing": "..."}"""

def format_context(context: list[dict]) -> str:
    return "\n\n".join(
        f"Source {n}: [{c['doc_type']} p.{c['page']}] (doc_date {c['doc_date']})\n{c['text']}"
        for n, c in enumerate(context, start=1))

def grade_context(state: RAGState) -> dict:
    llm = ChatOpenAI(model=config.GUARD_MODEL, temperature=0,
                     model_kwargs={"response_format": {"type": "json_object"}})
    prompt = f"QUESTION: {state['question']}\n\nCONTEXT:\n{format_context(state['context'])}"
    raw = llm.invoke([SystemMessage(GRADE_PROMPT), HumanMessage(prompt)]).content
    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        # fail OPEN: worst case we answer from what we have, and generate admits gaps
        verdict = {"grade": "SUFFICIENT", "missing": ""}
    grade = "INSUFFICIENT" if str(verdict.get("grade", "")).upper() == "INSUFFICIENT" else "SUFFICIENT"
    missing = verdict.get("missing", "") if grade == "INSUFFICIENT" else ""
    step = f"GRADE_CONTEXT: {grade}" + (f" (missing: {missing})" if missing else "")
    return {"grade": grade, "grade_feedback": missing, "steps": [step]}

# ---------------------------------------------------------------- 5. generate
ANSWER_PROMPT = """You answer questions about FlowDesk using ONLY the context.
Rules:
1. Cite every fact as [doc_type p.N].
2. If sources disagree, use the most recent doc_date and say that the older one is outdated.
3. If the context does not contain the answer, say so. Do not guess.
4. Never include personal contact details.
5. Roadmap items are plans unless the source says "Committed"."""

def generate(state: RAGState) -> dict:
    llm = ChatOpenAI(model=config.AGENT_MODEL, temperature=0)
    prompt = f"CONTEXT:\n{format_context(state['context'])}\n\nQUESTION: {state['question']}"
    response = llm.invoke([SystemMessage(ANSWER_PROMPT), HumanMessage(prompt)])
    return {"draft_answer": response.content, "steps": ["GENERATE: draft written"]}

# ---------------------------------------------------------------- 6. output guardrail
def output_guardrail(state: RAGState) -> dict:
    answer, pii_hits = mask_pii(state["draft_answer"])
    score, ungrounded = grounding_score(answer, state["context"])
    intent = state.get("sensitive_intent") or "none"
    needs_review = intent != "none" or score < config.GROUNDING_THRESHOLD
    report = {"pii_masked": pii_hits, "grounding": round(score, 2),
              "ungrounded_numbers": ungrounded, "sensitive_intent": intent}
    return {"draft_answer": answer, "guardrail_report": report, "needs_review": needs_review,
            "steps": [f"OUTPUT_GUARDRAIL: {report}"]}

# ---------------------------------------------------------------- 7. human review / finalise
def human_review(state: RAGState) -> dict:
    """Runs only AFTER the graph is resumed; state["review"] was set by main.py."""
    r = state.get("review") or {}
    decision = r.get("decision")
    if decision == "approve":
        final = state["draft_answer"]
    elif decision == "edit":
        final = r.get("edited") or state["draft_answer"]
    else:
        final = f"This answer was withheld by a reviewer. Reviewer note: {r.get('note') or '(none)'}"
    return {"final_answer": final, "steps": [f"HUMAN_REVIEW: {decision}"]}

def finalise(state: RAGState) -> dict:
    return {"final_answer": state["draft_answer"], "steps": ["FINALISE: auto-approved"]}
