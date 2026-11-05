"""
sub_agents_foundational.py
==========================

A FOUNDATIONAL, runnable example of the SUB-AGENT pattern
(also called the supervisor / orchestrator-worker pattern),
built with LangGraph and OpenAI GPT-4o.

--------------------------------------------------------------------------
WHAT THIS TEACHES
--------------------------------------------------------------------------
One SUPERVISOR coordinates several specialised SUB-AGENTS. On each turn the
supervisor:

    1. reads the user's request,
    2. decides which ONE specialist to consult next,
    3. hands that specialist a FOCUSED task,
    4. reads the finding that comes BACK,
    5. decides again -- consult another specialist, or stop and synthesise.

Steps 4 -> 5 are the heart of the pattern. Results return to the supervisor,
and the supervisor RE-DELEGATES based on what came back. That "come back and
decide" loop is exactly what separates a supervisor from a one-pass router
(a router fans out once, merges, and stops -- it never loops).

Domain: mutual-fund analysis. A user asks for a rounded view of a fund, and
the supervisor pulls together four specialists -- performance, holdings, risk,
and fees -- then composes a balanced summary.

--------------------------------------------------------------------------
WHAT IS DELIBERATELY LEFT OUT (and why)
--------------------------------------------------------------------------
- No retrieval / RAG / vector store. The fund data is a small hard-coded dict
  below, so the ONLY thing on screen is the control flow. The next project
  swaps this synthetic data for real retrieval -> a "sub-agentic RAG".
- The supervisor consults specialists ONE AT A TIME and re-decides after each,
  so the loop is visible. Production supervisors often fan several out in
  parallel; that is an optimisation on top of the same idea.

--------------------------------------------------------------------------
HOW TO RUN
--------------------------------------------------------------------------
    pip install langgraph langchain-openai
    export OPENAI_API_KEY=sk-...
    python sub_agents_foundational.py
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
load_dotenv(override=True)
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

import time
import logging
import re

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================================================================
# 0. THE MODEL
# ===========================================================================
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# Robust wrapper for different LangChain/LLM return shapes with retries.
def call_llm(messages, retries: int = 3, backoff: float = 1.0) -> str:
    """Call the LLM and return a normalized string. Retries on failure."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            response = None
            try:
                response = llm(messages)
            except Exception as e_call:
                try:
                    response = llm.generate([messages])
                except Exception:
                    raise e_call

            if response is None:
                raise RuntimeError("Empty response from LLM")

            # Normalize many possible response shapes
            if isinstance(response, str):
                text = response
            elif hasattr(response, "content"):
                text = getattr(response, "content")
            elif hasattr(response, "generations"):
                gens = getattr(response, "generations")
                if isinstance(gens, list) and gens:
                    first = gens[0]
                    if isinstance(first, list) and first:
                        candidate = first[0]
                        text = getattr(candidate, "text", None) or (candidate.get("text") if isinstance(candidate, dict) else None)
                    else:
                        candidate = first
                        text = getattr(candidate, "text", None) or (candidate.get("text") if isinstance(candidate, dict) else None)
                else:
                    text = str(response)
            elif isinstance(response, dict):
                text = response.get("content") or response.get("text") or str(response)
            else:
                text = str(response)

            if not isinstance(text, str):
                text = str(text)
            return text.strip()
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM call failed (attempt %d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(backoff * (2 ** (attempt - 1)))
            else:
                logger.error("LLM call failed after %d attempts", retries)
    raise last_exc

# ===========================================================================
# 1. SYNTHETIC FUND DATA
# ===========================================================================
FUND_DATA = {
    "Bluechip Equity Fund": {
        "performance": (
            "1Y: 22.4%. 3Y: 16.1% CAGR. 5Y: 14.8% CAGR. "
            "Benchmark (Nifty 100 TRI) 5Y: 13.2%. Beats benchmark over 3Y and 5Y."
        ),
        "holdings": (
            "Top holdings: HDFC Bank 9.1%, ICICI Bank 7.8%, Reliance 6.4%, "
            "Infosys 5.2%, L&T 4.0%. Sectors: Financials 34%, IT 15%, Energy 11%. "
            "Top-10 concentration: 48%."
        ),
        "risk": (
            "Std deviation 13.2% (category avg 14.1%). Sharpe 1.02. "
            "Max drawdown over 5Y: -18.6%. Beta 0.94. Lower risk than category average."
        ),
        "fees": (
            "Expense ratio 1.12% (direct plan 0.68%). Exit load 1% if redeemed within "
            "365 days. Equity taxation: LTCG 12.5% above Rs 1.25L after 1Y; STCG 20%."
        ),
    }
}

SPECIALISTS = ["performance", "holdings", "risk", "fees"]
MAX_STEPS = 8

# ===========================================================================
# 2. SHARED STATE
# ===========================================================================
class State(TypedDict):
    request: str
    fund_name: str
    findings: dict
    next_step: str
    final_answer: str
    steps: int

# Precompile regex patterns for parsing
DONE_RE = re.compile(r"\bdone\b", flags=re.IGNORECASE)
# compile per-specialist patterns lazily in supervisor

# ===========================================================================
# 3. THE SUPERVISOR
# ===========================================================================
def supervisor(state: State) -> dict:
    consulted = list(state["findings"].keys())
    remaining = [s for s in SPECIALISTS if s not in consulted]

    if state["steps"] >= MAX_STEPS or not remaining:
        return {"next_step": "DONE", "steps": state["steps"] + 1}

    system = SystemMessage(content=(
        "You are a supervisor coordinating mutual-fund analysts. Given the user's "
        "request and the findings gathered so far, decide the SINGLE next analyst to "
        "consult, or answer DONE if you already have enough for a rounded view.\n"
        f"Analysts still unconsulted: {remaining}\n"
        "Reply with EXACTLY one word: one analyst name from that list, or DONE."
    ))
    human = HumanMessage(content=(
        f"Request: {state['request']}\n"
        f"Fund: {state['fund_name']}\n"
        f"Findings so far: {state['findings'] or 'none yet'}"
    ))

    try:
        decision_raw = call_llm([system, human])
    except Exception as exc:
        logger.error("Supervisor LLM failed: %s", exc)
        return {"next_step": remaining[0], "steps": state["steps"] + 1}

    decision = decision_raw.strip()

    if DONE_RE.search(decision):
        choice = "DONE"
    else:
        matched = None
        for s in remaining:
            if re.search(rf"\b{re.escape(s)}\b", decision, flags=re.IGNORECASE):
                matched = s
                break
        choice = matched or remaining[0]

    logger.info("Supervisor chose: %s (raw: %s)", choice, decision_raw)
    return {"next_step": choice, "steps": state["steps"] + 1}

# ===========================================================================
# 4. THE SPECIALISTS (the sub-agents)
# ===========================================================================
def _consult(state: State, role: str, brief: str, data_key: str) -> dict:
    fund = state.get("fund_name")
    if fund not in FUND_DATA:
        err = f"ERROR: unknown fund '{fund}'"
        logger.error(err)
        return {"findings": {**state["findings"], data_key: err}}

    if data_key not in FUND_DATA[fund]:
        err = f"ERROR: missing data key '{data_key}' for fund '{fund}'"
        logger.error(err)
        return {"findings": {**state["findings"], data_key: err}}

    data_slice = FUND_DATA[fund][data_key]

    system = SystemMessage(content=(
        f"You are a mutual-fund {role}. {brief} "
        "Base your answer ONLY on the data provided. Be concise: 2-3 sentences."
    ))
    human = HumanMessage(content=f"Fund: {fund}\nData:\n{data_slice}")

    try:
        finding_text = call_llm([system, human])
    except Exception as exc:
        logger.error("Specialist '%s' LLM failed: %s", role, exc)
        finding_text = f"ERROR: specialist '{role}' failed to produce a finding."

    return {"findings": {**state["findings"], data_key: finding_text}}

def performance_agent(state: State) -> dict:
    return _consult(state, "performance analyst",
                    "Assess returns versus the benchmark and consistency.",
                    "performance")

def holdings_agent(state: State) -> dict:
    return _consult(state, "portfolio analyst",
                    "Comment on holdings, sector mix, and concentration risk.",
                    "holdings")

def risk_agent(state: State) -> dict:
    return _consult(state, "risk analyst",
                    "Interpret volatility, drawdown, and risk-adjusted return.",
                    "risk")

def fees_agent(state: State) -> dict:
    return _consult(state, "fees and tax analyst",
                    "Explain expense ratio, exit load, and tax on redemption.",
                    "fees")

# ===========================================================================
# 5. SYNTHESIS
# ===========================================================================
def synthesise(state: State) -> dict:
    system = SystemMessage(content=(
        "You are the lead advisor. Combine the analysts' findings into a short, "
        "balanced view of the fund for an investor. 4-6 sentences. Do not invent data."
    ))
    human = HumanMessage(content=(
        f"Request: {state['request']}\n"
        f"Fund: {state['fund_name']}\n"
        "Analyst findings:\n"
        + "\n".join(f"- {name}: {text}" for name, text in state["findings"].items())
    ))
    try:
        answer = call_llm([system, human])
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc)
        answer = "ERROR: synthesis failed."

    return {"final_answer": answer}

# ===========================================================================
# 6. ROUTING + GRAPH WIRING
# ===========================================================================
def route(state: State) -> str:
    if state["next_step"] == "DONE":
        return "synthesise"
    return state["next_step"]

def build_graph():
    g = StateGraph(State)
    g.add_node("supervisor", supervisor)
    g.add_node("performance", performance_agent)
    g.add_node("holdings", holdings_agent)
    g.add_node("risk", risk_agent)
    g.add_node("fees", fees_agent)
    g.add_node("synthesise", synthesise)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor",
        route,
        {
            "performance": "performance",
            "holdings": "holdings",
            "risk": "risk",
            "fees": "fees",
            "synthesise": "synthesise",
        },
    )
    for specialist in SPECIALISTS:
        g.add_edge(specialist, "supervisor")
    g.add_edge("synthesise", END)
    return g.compile()

# ===========================================================================
# 7. RUN IT
# ===========================================================================
if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY before running.")

    app = build_graph()

    initial: State = {
        "request": "I'm considering this fund. Give me a rounded view before I invest.",
        "fund_name": "Bluechip Equity Fund",
        "findings": {},
        "next_step": "",
        "final_answer": "",
        "steps": 0,
    }

    for event in app.stream(initial):
        for node, update in event.items():
            print(f"\n=== {node} ===")
            if node == "supervisor":
                print("supervisor decided ->", update.get("next_step"))
            elif node == "synthesise":
                print(update.get("final_answer"))
            else:
                newest_key = list(update["findings"].keys())[-1]
                print(update["findings"][newest_key])