r"""
handoffs_foundational.py
========================

A FOUNDATIONAL, runnable example of the HANDOFFS pattern, built with LangGraph and
OpenAI GPT-4o. Companion to sub_agents_foundational.py and router_foundational.py.

--------------------------------------------------------------------------
WHAT MAKES HANDOFFS DIFFERENT
--------------------------------------------------------------------------
Sub-agents and Router have a coordinator that stays in charge. Handoffs has no
coordinator: the ACTIVE agent changes as the conversation moves through stages, and
each agent TRANSFERS control to the next when its part is done.

Three properties define the pattern, and this file shows all three:

  1. Control transfer  -- each stage agent "hands off" to the next by setting who is
     active next. (In a real system this is a tool the agent calls; here each agent
     sets a `handoff` field, and routing activates that stage.)
  2. State carried forward -- details collected in one stage are available in later
     stages. A MemorySaver checkpointer persists state across the user's turns.
  3. Sequential stage-gating -- a stage unlocks only after the previous one finishes.
     You cannot reach eligibility before intake is complete, or submission before the
     applicant is found eligible. The graph's structure enforces this.

Domain: a loan-application assistant.  intake -> eligibility -> submit

    START -> intake (collect details) --handoff--> eligibility (check)
              |                                        |
         [user turn]                           eligible? --> submit (confirm) --> END
                                                     \--> rejected --> END

--------------------------------------------------------------------------
HOW THE USER TURNS WORK
--------------------------------------------------------------------------
The graph runs as ONE session that PAUSES (via interrupt) whenever it needs input
from the applicant -- once in intake (to collect details) and once in submit (to
confirm). Between pauses, control is handed from agent to agent automatically.

--------------------------------------------------------------------------
HOW TO RUN
--------------------------------------------------------------------------
    pip install langgraph langchain-openai
    export OPENAI_API_KEY=sk-...
    python handoffs_foundational.py
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
load_dotenv(override=True)
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

REQUIRED = ["name", "monthly_income", "loan_amount", "tenure_months"]


# ===========================================================================
# STATE
# ---------------------------------------------------------------------------
# Persisted across the user's turns by the checkpointer. `handoff` is the field an
# agent sets to name who should be active next -- it is the handoff mechanism.
# ===========================================================================
class State(TypedDict):
    applicant: dict
    eligible: Optional[bool]
    reference: str
    handoff: str
    reply: str

# single shared LLM client for simplicity
llm = ChatOpenAI(model="gpt-4o", temperature=0)


def _say(role: str, instruction: str) -> str:
    system = SystemMessage(content=(
        f"You are the {role} agent in a loan-application assistant. {instruction} "
        "Keep it to one or two short, friendly sentences."
    ))
    return llm.invoke([system, HumanMessage(content="Write your message.")]).content.strip()


def intake(state: State) -> dict:
    applicant = dict(state.get("applicant", {}))
    missing = set(REQUIRED) - applicant.keys()
    if missing:
        msg = _say("intake",
                   "Ask the applicant for their full name, monthly income in INR, the "
                   "loan amount they want in INR, and the tenure in months.")
        provided = interrupt({"agent": "intake", "message": msg, "need": REQUIRED})
        applicant.update(provided)

    return {"applicant": applicant, "handoff": "eligibility", "reply": "Intake complete."}


def eligibility(state: State) -> dict:
    a = state["applicant"]
    try:
        emi = float(a["loan_amount"]) / float(a["tenure_months"])
        eligible = emi <= 0.5 * float(a["monthly_income"])
    except Exception:
        eligible = False
        emi = 0.0

    verdict = "eligible" if eligible else "not eligible"
    msg = _say("eligibility",
               f"Tell the applicant they are {verdict}. Their estimated EMI is about "
               f"{emi:.0f} against a monthly income of {a.get('monthly_income', 'N/A')}.")
    return {"eligible": eligible,
            "handoff": "submit" if eligible else "rejected",
            "reply": msg}


def submit(state: State) -> dict:
    a = state["applicant"]
    msg = _say("submission",
               f"Ask {a.get('name','applicant')} to confirm they want to submit the application now. "
               "Tell them to reply yes or no.")
    confirm = interrupt({"agent": "submit", "message": msg})
    if str(confirm).strip().lower().startswith("y"):
        return {"reference": "LN-2026-00042", "handoff": "done", "reply": "Application submitted."}
    return {"handoff": "cancelled", "reply": "Submission cancelled."}


def rejected(state: State) -> dict:
    msg = _say("eligibility",
               "Politely explain the application can't proceed and suggest reducing the "
               "loan amount or extending the tenure.")
    return {"handoff": "done", "reply": msg}


def route(state: State) -> str:
    return state.get("handoff", "")


def build_graph() -> StateGraph:
    g = StateGraph(State)
    # register stages directly (no lambdas)
    g.add_node("intake", intake)
    g.add_node("eligibility", eligibility)
    g.add_node("submit", submit)
    g.add_node("rejected", rejected)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", route, {"eligibility": "eligibility"})
    g.add_conditional_edges("eligibility", route, {"submit": "submit", "rejected": "rejected"})
    g.add_conditional_edges("submit", route, {"done": END, "cancelled": END})
    g.add_edge("rejected", END)

    return g.compile(checkpointer=MemorySaver())


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY before running.")

    app = build_graph()
    config = {"configurable": {"thread_id": "loan-1"}}

    state: State = {"applicant": {}, "eligible": None, "reference": "",
                    "handoff": "", "reply": ""}

    result = app.invoke(state, config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print(f"\n[{payload['agent']} agent] {payload['message']}")

        if payload["agent"] == "intake":
            provided = {}
            for field in payload["need"]:
                provided[field] = input(f"  {field}: ").strip()
            for f in ("monthly_income", "loan_amount", "tenure_months"):
                provided[f] = float(provided[f])
            resume_value = provided
        else:
            resume_value = input("  your answer: ").strip()

        result = app.invoke(Command(resume=resume_value), config)

    print("\n----- OUTCOME -----")
    if result.get("reference"):
        print(f"Eligible and submitted. Reference: {result['reference']}")
    elif result.get("eligible") is False:
        print("Not eligible.")
    else:
        print(result.get("reply", "Session ended."))
