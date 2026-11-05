"""
=====================================================================
FILE: app/supervisor.py
=====================================================================
PURPOSE
    Builds the LangGraph graph with 1 supervisor and 3 subagents:

              +------------> extractor ---+
              |                           |
    START -> supervisor <-----------------+
              |  ^                        |
              |  +------- analyst <-------+ (each subagent returns
              |  +------- writer  <-------+  to the supervisor)
              |
              +--> END  (when supervisor says FINISH)

    Every turn the supervisor (an LLM) looks at what is already done,
    picks the next subagent, and writes that subagent's task. The
    subagent runs and hands its result back to the supervisor.
    So the order becomes: extractor -> analyst -> writer -> FINISH.

WHAT PROBLEM IT SOLVES
    The supervisor plans and delegates; it never reads the PDFs itself.
    Each subagent gets a small, focused input. The supervisor only sees
    short summaries of what each subagent finished.

HOW TO RUN
    Not run directly. Used by main.py.

EXPECTED OUTPUT
    build_graph() returns a compiled graph.
=====================================================================
"""

# json parses the supervisor's JSON reply.
import json

# operator.add joins trace lists from each step.
import operator

# perf_counter measures how long each step takes.
import time

# Annotated attaches the reducer; TypedDict defines the state shape.
from typing import Annotated, TypedDict

# StateGraph builds the graph; START/END are the entry and exit.
from langgraph.graph import StateGraph, START, END

# Shared LLM helper.
from app.llm import call_llm

# The 3 subagent functions.
from app.subagents import extractor, analyst, writer


# Fixed order the work must follow, used to check the supervisor's choice.
ORDER = ["extractor", "analyst", "writer"]


class State(TypedDict):
    # The overall goal given by the user.
    goal: str
    # Outputs of finished subagents: {"extractor": "...", "analyst": "..."}.
    results: dict
    # Name of the subagent the supervisor picked (or "FINISH").
    next: str
    # Task the supervisor wrote for that subagent.
    instruction: str
    # Log of every step; operator.add appends instead of overwriting.
    trace: Annotated[list, operator.add]


def supervisor_node(state: State) -> dict:
    """Decide which subagent runs next and write its task."""
    # Start the step timer.
    t = time.perf_counter()
    # Names of subagents already finished.
    done = list(state["results"])
    # The supervisor sees only the FIRST 150 characters of each result:
    # enough to know the work is done, not the full detail.
    summaries = "\n".join(f"- {k}: {v[:150]}..." for k, v in state["results"].items()) or "- nothing yet"
    # Supervisor's role: describe the team and the reply format.
    system = (
        "You are a supervisor agent managing three subagents:\n"
        "- extractor: reads the job description and resume PDFs and extracts facts\n"
        "- analyst: compares the extracted facts, finds matches and gaps\n"
        "- writer: writes the final decision note from the analysis\n"
        "Each subagent needs the previous one's output. Pick the next subagent, or FINISH when all three are done.\n"
        'Reply ONLY with JSON: {"next": "<extractor|analyst|writer|FINISH>", "instruction": "<one-sentence task>"}'
    )
    # Goal and progress so far.
    user = f"Goal: {state['goal']}\nFinished so far:\n{summaries}"
    # Ask the LLM to decide.
    reply = call_llm(system, user)
    # Try to read the JSON reply.
    try:
        # Parse the JSON text into a dict.
        decision = json.loads(reply)
    # If the reply is not valid JSON, use an empty decision.
    except json.JSONDecodeError:
        decision = {}
    # The correct next step: first subagent not yet done, else FINISH.
    expected = next((name for name in ORDER if name not in done), "FINISH")
    # The supervisor's choice.
    chosen = decision.get("next")
    # Guardrail: if the LLM picked something invalid or out of order, use the correct step.
    accepted = chosen == expected
    # Final choice after the check.
    final = chosen if accepted else expected
    # The task text; fall back to the goal if the LLM gave none.
    instruction = decision.get("instruction") or state["goal"]
    # Save the decision and log the step.
    return {
        "next": final,
        "instruction": instruction,
        "trace": [{
            "step": "supervisor",
            "decided": final,
            "llm_choice_accepted": accepted,
            "instruction": instruction,
            "ms": round((time.perf_counter() - t) * 1000),
        }],
    }


def run_subagent(name: str, func, needs: str | None):
    """Create a graph node that runs one subagent with only its needed input."""

    def node(state: State) -> dict:
        # Start the step timer.
        t = time.perf_counter()
        # Pass only the previous subagent's output (if this one needs it).
        output = func(state["instruction"]) if needs is None else func(state["instruction"], state["results"][needs])
        # Add this result without changing the others.
        results = {**state["results"], name: output}
        # Return results and a log entry; control goes back to the supervisor.
        return {
            "results": results,
            "trace": [{
                "step": name,
                "received": needs or "the 2 PDFs",
                "output_chars": len(output),
                "ms": round((time.perf_counter() - t) * 1000),
            }],
        }

    # Return the node function.
    return node


def route(state: State) -> str:
    """Read the supervisor's decision and send the graph there."""
    # "extractor" / "analyst" / "writer" / "FINISH".
    return state["next"]


def build_graph():
    """Wire the supervisor and the 3 subagents together."""
    # New graph using our State.
    g = StateGraph(State)
    # Add the supervisor.
    g.add_node("supervisor", supervisor_node)
    # Extractor reads the PDFs itself, so it needs no previous output.
    g.add_node("extractor", run_subagent("extractor", extractor, needs=None))
    # Analyst needs the extractor's facts.
    g.add_node("analyst", run_subagent("analyst", analyst, needs="extractor"))
    # Writer needs the analyst's analysis.
    g.add_node("writer", run_subagent("writer", writer, needs="analyst"))
    # The graph always starts at the supervisor.
    g.add_edge(START, "supervisor")
    # From the supervisor, go wherever route() says.
    g.add_conditional_edges(
        "supervisor",
        route,
        {"extractor": "extractor", "analyst": "analyst", "writer": "writer", "FINISH": END},
    )
    # Every subagent reports back to the supervisor.
    for name in ORDER:
        g.add_edge(name, "supervisor")
    # Validate and return the runnable graph.
    return g.compile()
