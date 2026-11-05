"""The agentic RAG workflow — this is where everything from the series comes together.

Flow:
  expand  ->  [retrieve_1, retrieve_2, retrieve_3]   (FAN-OUT: 3 retrievers at once)
          ->  merge                                   (FAN-IN: dedupe via a reducer)
          ->  grade                                   (the AGENTIC self-check)
          ->  sufficient?  -> generate
              insufficient? -> broaden -> generate    (fetch more, then answer)

The two reducers (`chunks`, `retrieval_log`) are the reason three parallel
retrievers can safely write into shared state in the same round.
"""
import time
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

import llm
from vectorstore import build_store

NUM_RETRIEVERS = 3
TOP_K = 4

store = build_store()  # read + embed the PDFs once, when this module first loads


# --- state -----------------------------------------------------------
# `chunks` and `retrieval_log` are written by all three retrievers in the SAME
# round, so both need a REDUCER (`add`) to append the writes instead of letting
# them collide. This is the exact lesson from the voting project, now in a real
# system. Remove a reducer and the parallel retrieval crashes at the fan-in.
class State(TypedDict):
    question: str
    sub_queries: list
    chunks: Annotated[list, add]         # every retriever appends its hits here
    retrieval_log: Annotated[list, add]  # every retriever appends its stats here
    context: str
    total_hits: int
    unique_hits: int
    grade: str
    grade_reason: str
    broadened: bool
    answer: str
    sources: list


def _dedupe(chunks):
    """Keep the highest-scoring copy of each chunk id (parallel branches overlap)."""
    best = {}
    for c in chunks:
        if c["id"] not in best or c["score"] > best[c["id"]]["score"]:
            best[c["id"]] = c
    return sorted(best.values(), key=lambda c: c["score"], reverse=True)


def _format_context(chunks):
    return "\n\n".join(f"[{c['source']}] {c['text']}" for c in chunks)


# --- nodes -----------------------------------------------------------
def expand(state: State) -> dict:
    """Turn one question into several focused sub-queries."""
    return {"sub_queries": llm.expand_queries(state["question"], NUM_RETRIEVERS)}


def make_retriever(i: int):
    """Retriever i searches with sub-query i, then appends its hits AND its stats."""
    def retrieve(state: State) -> dict:
        query = state["sub_queries"][i]
        t = time.perf_counter()
        hits = store.search(query, TOP_K)
        dur = time.perf_counter() - t
        return {
            "chunks": hits,  # goes into the shared list via the reducer
            "retrieval_log": [{
                "retriever": i + 1, "query": query, "hits": len(hits),
                "top_source": hits[0]["source"] if hits else "-",
                "seconds": dur,
            }],
        }
    return retrieve


def merge(state: State) -> dict:
    """Fan-in: dedupe everything the parallel retrievers appended into one context."""
    unique = _dedupe(state["chunks"])
    return {
        "context": _format_context(unique),
        "total_hits": len(state["chunks"]),
        "unique_hits": len(unique),
    }


def grade(state: State) -> dict:
    """The agentic self-check: is the retrieved context good enough to answer?"""
    verdict, reason = llm.grade_context(state["question"], state["context"])
    return {"grade": verdict, "grade_reason": reason}


def broaden(state: State) -> dict:
    """Taken only when grade said 'insufficient': one broader retrieval on the whole
    question, appended to the same shared chunks box (the reducer merges it in)."""
    return {"chunks": store.search(state["question"], TOP_K + 2), "broadened": True}


def generate(state: State) -> dict:
    """Write the final answer from the (possibly broadened) deduped context."""
    unique = _dedupe(state["chunks"])
    context = _format_context(unique)
    answer = llm.generate_answer(state["question"], context)
    return {"answer": answer, "context": context,
            "unique_hits": len(unique), "sources": sorted({c["source"] for c in unique})}


def route_after_grade(state: State) -> str:
    """Conditional edge: answer now, or fetch more first."""
    return "generate" if state["grade"] == "sufficient" else "broaden"


# --- wiring ----------------------------------------------------------
def build_rag_graph():
    g = StateGraph(State)
    g.add_node("expand", expand)
    for i in range(NUM_RETRIEVERS):
        g.add_node(f"retrieve_{i + 1}", make_retriever(i))
    g.add_node("merge", merge)
    g.add_node("grade", grade)
    g.add_node("broaden", broaden)
    g.add_node("generate", generate)

    g.add_edge(START, "expand")
    for i in range(NUM_RETRIEVERS):
        g.add_edge("expand", f"retrieve_{i + 1}")   # fan-out: 3 retrievers in one round
        g.add_edge(f"retrieve_{i + 1}", "merge")     # fan-in: merge waits for all 3
    g.add_edge("merge", "grade")
    g.add_conditional_edges("grade", route_after_grade,
                            {"generate": "generate", "broaden": "broaden"})
    g.add_edge("broaden", "generate")
    g.add_edge("generate", END)
    return g.compile()