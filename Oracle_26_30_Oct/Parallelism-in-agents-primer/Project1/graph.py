"""The parallel-summary workflow: state, nodes, and two wirings of the same nodes.

The prints inside the nodes are here only so the classroom can SEE the timeline.
In real code you would use logging or LangGraph callbacks instead.
"""
import time
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

from llm import summarize_text, make_digest

# --- shared clock, so every print shows time since the run started ---
_T0 = time.perf_counter()


def reset_clock() -> None:
    global _T0
    _T0 = time.perf_counter()


def _elapsed() -> float:
    return time.perf_counter() - _T0


# --- state -----------------------------------------------------------
# `summaries` is the shared box all three branches write to at once.
# The `add` reducer says: don't overwrite — append each branch's result.
# Remove the reducer and the parallel run errors, because LangGraph won't
# know which of the three writes to keep.
class State(TypedDict):
    documents: list[str]
    summaries: Annotated[list, add]
    digest: str


# --- nodes -----------------------------------------------------------
def make_summarizer(i: int):
    """Build the node that summarizes document i and appends (i, summary)."""
    def summarize(state: State) -> dict:
        t = time.perf_counter()
        summary = summarize_text(state["documents"][i])
        dur = time.perf_counter() - t
        print(f"[{_elapsed():5.2f}s]    done doc {i + 1}   (took {dur:.2f}s)")
        return {"summaries": [(i, summary)]}
    return summarize


def combine(state: State) -> dict:
    """Runs only after all three summaries exist — so it can't be parallelized."""
    t = time.perf_counter()
    ordered = [s for _, s in sorted(state["summaries"])]  # sort by doc index
    digest = make_digest(ordered)
    dur = time.perf_counter() - t
    print(f"[{_elapsed():5.2f}s]  fan-in: digest ready   (combine took {dur:.2f}s)")
    return {"digest": digest}


# --- two wirings of the SAME nodes -----------------------------------
def _add_nodes(g: StateGraph) -> None:
    g.add_node("summarize_doc_1", make_summarizer(0))
    g.add_node("summarize_doc_2", make_summarizer(1))
    g.add_node("summarize_doc_3", make_summarizer(2))
    g.add_node("combine", combine)


def build_parallel_graph():
    """START fans out to all three; they fan in to combine."""
    g = StateGraph(State)
    _add_nodes(g)
    for name in ("summarize_doc_1", "summarize_doc_2", "summarize_doc_3"):
        g.add_edge(START, name)      # fan-out: all three start in one round
        g.add_edge(name, "combine")  # fan-in: combine waits for all three
    g.add_edge("combine", END)
    return g.compile()


def build_linear_graph():
    """The same nodes, chained one after another."""
    g = StateGraph(State)
    _add_nodes(g)
    g.add_edge(START, "summarize_doc_1")
    g.add_edge("summarize_doc_1", "summarize_doc_2")
    g.add_edge("summarize_doc_2", "summarize_doc_3")
    g.add_edge("summarize_doc_3", "combine")
    g.add_edge("combine", END)
    return g.compile()