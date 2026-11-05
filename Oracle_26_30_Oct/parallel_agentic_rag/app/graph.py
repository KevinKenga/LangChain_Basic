"""
=====================================================================
FILE: app/graph.py
=====================================================================
PURPOSE
    Builds the LangGraph graph:
        START --> customer_voice  --\
        START --> usage_analytics ---\
        START --> market           ---> synthesizer --> END
        START --> risk             --/
    The 4 agent nodes have no edges between them, so LangGraph runs
    them in the SAME step, in parallel (each in its own thread).
    The synthesizer has 4 incoming edges, so it waits for all 4.

WHAT PROBLEM IT SOLVES
    Each agent spends most of its time waiting on network calls
    (embedding API, LLM API). Running them one after another means
    the total time = sum of all 4. Running them in parallel means the
    total time is about the time of the slowest one.

    Every node records its own start time, end time and a split of
    retrieve / re-rank / LLM milliseconds, so the UI can prove this.

HOW TO RUN
    Used by app/server.py. Not run directly.

EXPECTED OUTPUT
    run_question() returns a dict with "agents", "synthesizer",
    "wall_clock_ms" and "sum_of_agents_ms".
=====================================================================
"""

# operator.add is used as a "reducer": it tells LangGraph to JOIN the
# lists returned by parallel nodes instead of overwriting each other.
import operator

# perf_counter is a high-precision clock, good for measuring durations.
import time

# Annotated attaches the reducer to a state field; TypedDict defines the state shape.
from typing import Annotated, TypedDict

# StateGraph builds the graph; START and END are the fixed entry/exit points.
from langgraph.graph import StateGraph, START, END

# OpenAI client for chat completions.
from openai import OpenAI

# Our settings.
from app import config


# ---------------------------------------------------------------------
# STATE: the data that flows through the graph.
# ---------------------------------------------------------------------
class GraphState(TypedDict):
    # The user's question.
    question: str
    # perf_counter() value at the moment the request began; all node
    # times are measured relative to this.
    t0: float
    # Results from the 4 agents. operator.add JOINS the 4 one-item lists
    # into one 4-item list. Without it, parallel writes would clash.
    agent_results: Annotated[list, operator.add]
    # Final output from the synthesizer.
    synthesis: dict


# ---------------------------------------------------------------------
# AGENT DEFINITIONS: 4 nodes, each with a different task.
# ---------------------------------------------------------------------
AGENTS = [
    {
        # Node name inside the graph.
        "name": "customer_voice",
        # Label shown in the UI.
        "label": "Customer Voice Agent",
        # Only search the feedback PDF.
        "sources": ["feedback"],
        # Extra words added to the search query to focus this agent's task.
        "query_focus": "customer requests complaints feedback",
        # Task instruction given to the LLM.
        "task": "Report what customers are asking for and complaining about that relates to the question.",
    },
    {
        "name": "usage_analytics",
        "label": "Usage Analytics Agent",
        # Only search the analytics PDF.
        "sources": ["analytics"],
        "query_focus": "churn adoption response time metrics numbers",
        "task": "Report the usage numbers (churn, adoption, response times, pilot results) that relate to the question.",
    },
    {
        "name": "market",
        "label": "Market Agent",
        # Only search the competitor PDF.
        "sources": ["competitor"],
        "query_focus": "competitors pricing lost deals",
        "task": "Report what competitors offer, their pricing, and deals we lost that relate to the question.",
    },
    {
        "name": "risk",
        "label": "Risk Agent",
        # Search ALL 3 PDFs: risks can hide anywhere.
        "sources": list(config.PDF_FILES),
        "query_focus": "risks concerns costs fees privacy wrong answers",
        "task": "Report risks, concerns or costs that could make this a bad idea. Be critical.",
    },
]


def call_llm(client: OpenAI, system: str, user: str) -> str:
    """Send one chat request and return the reply text."""
    # temperature=0 -> same answer for same input; good for demos.
    response = client.chat.completions.create(
        # Which model to use.
        model=config.LLM_MODEL,
        # Deterministic output.
        temperature=0,
        # System message sets the role; user message carries the data.
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    # Return just the text of the first (only) reply.
    return response.choices[0].message.content


def make_agent_node(agent: dict, store, reranker, client: OpenAI):
    """Create the node function for one agent. Same code, different settings."""

    def node(state: GraphState) -> dict:
        # Clock reading when this node starts.
        node_start = time.perf_counter()

        # --- Step 1: RETRIEVE (vector search) ---
        # Combine the question with this agent's focus words.
        search_query = f"{state['question']} {agent['query_focus']}"
        # Get the top 10 chunks from this agent's PDFs.
        candidates = store.search(search_query, config.RETRIEVE_TOP_K, agent["sources"])
        # Clock reading after retrieval.
        t_retrieved = time.perf_counter()

        # --- Step 2: RE-RANK (cross-encoder) ---
        # Re-rank with the plain question (what the user actually asked).
        reranked = reranker.rerank(state["question"], candidates, config.RERANK_TOP_N)
        # Keep only the chunks marked as kept (top 3).
        kept = [c for c in reranked if c["kept"]]
        # Clock reading after re-ranking.
        t_reranked = time.perf_counter()

        # --- Step 3: ANSWER (LLM) ---
        # Format each kept chunk with its source and page so the LLM can cite it.
        context = "\n\n".join(f"[{c['source']} p.{c['page']}] {c['text']}" for c in kept)
        # Instructions: do this agent's task, use only the context, cite pages.
        system = (
            f"You are the {agent['label']} at NimbusDesk. {agent['task']} "
            "Use ONLY the context. Cite like [source p.N]. Reply in 3-4 short bullet points."
        )
        # Ask the LLM.
        finding = call_llm(client, system, f"Question: {state['question']}\n\nContext:\n{context}")
        # Clock reading at the end of the node.
        node_end = time.perf_counter()

        # Return a ONE-item list; the operator.add reducer joins it with the other agents' lists.
        return {
            "agent_results": [
                {
                    # Node name and display label.
                    "name": agent["name"],
                    "label": agent["label"],
                    # Which PDFs this agent searched.
                    "sources": agent["sources"],
                    # The LLM's finding.
                    "finding": finding,
                    # Start/end in ms since the request began -> lets the UI draw the timeline.
                    "start_ms": round((node_start - state["t0"]) * 1000, 1),
                    "end_ms": round((node_end - state["t0"]) * 1000, 1),
                    # Total time spent inside this node.
                    "duration_ms": round((node_end - node_start) * 1000, 1),
                    # Split of where the time went.
                    "retrieve_ms": round((t_retrieved - node_start) * 1000, 1),
                    "rerank_ms": round((t_reranked - t_retrieved) * 1000, 1),
                    "llm_ms": round((node_end - t_reranked) * 1000, 1),
                    # All 10 chunks with both ranks, for the before/after table.
                    "chunks": reranked,
                }
            ]
        }

    # Hand back the node function (it "remembers" agent, store, reranker, client).
    return node


def make_synthesizer_node(client: OpenAI):
    """Create the fan-in node that combines the 4 findings."""

    def synthesizer(state: GraphState) -> dict:
        # Clock reading when the synthesizer starts (after all 4 agents finish).
        node_start = time.perf_counter()
        # Put each agent's finding under its label.
        findings = "\n\n".join(f"## {r['label']}\n{r['finding']}" for r in state["agent_results"])
        # Instructions for the final recommendation.
        system = (
            "You are the Head of Product at NimbusDesk. Using ONLY the four agent findings, "
            "give a recommendation. Start with one line: 'Decision: Build now', 'Decision: Build later' "
            "or 'Decision: Don't build'. Then 3-5 bullet reasons, keeping the citations [source p.N]. "
            "Then one line starting 'Main risk:'."
        )
        # Ask the LLM.
        answer = call_llm(client, system, f"Question: {state['question']}\n\n{findings}")
        # Clock reading at the end.
        node_end = time.perf_counter()
        # Store the synthesizer's answer and its timings.
        return {
            "synthesis": {
                "answer": answer,
                "start_ms": round((node_start - state["t0"]) * 1000, 1),
                "end_ms": round((node_end - state["t0"]) * 1000, 1),
                "duration_ms": round((node_end - node_start) * 1000, 1),
            }
        }

    # Hand back the node function.
    return synthesizer


def build_graph(store, reranker, client: OpenAI):
    """Wire up the nodes and edges, return a compiled graph."""
    # Create a graph that carries GraphState between nodes.
    graph = StateGraph(GraphState)
    # Add the 4 agent nodes.
    for agent in AGENTS:
        # Register the node under its name.
        graph.add_node(agent["name"], make_agent_node(agent, store, reranker, client))
        # FAN-OUT: START -> agent. 4 edges from START = 4 nodes in the same step = parallel.
        graph.add_edge(START, agent["name"])
    # Add the synthesizer node.
    graph.add_node("synthesizer", make_synthesizer_node(client))
    # FAN-IN: passing a LIST of sources means "wait for ALL of these before running".
    graph.add_edge([a["name"] for a in AGENTS], "synthesizer")
    # After the synthesizer, the graph ends.
    graph.add_edge("synthesizer", END)
    # Compile = validate the wiring and produce a runnable object.
    return graph.compile()


def run_question(app_graph, question: str) -> dict:
    """Run one question through the graph and add the timing totals."""
    # Start the request clock.
    t0 = time.perf_counter()
    # Run the graph. agent_results starts empty; the reducer fills it.
    result = app_graph.invoke({"question": question, "t0": t0, "agent_results": [], "synthesis": {}})
    # Total time the user waited.
    wall_clock_ms = round((time.perf_counter() - t0) * 1000, 1)
    # Sort agents by start time so the UI lists them in launch order.
    agents = sorted(result["agent_results"], key=lambda r: r["start_ms"])
    # What the 4 agents would cost if run one after another.
    sum_of_agents_ms = round(sum(a["duration_ms"] for a in agents), 1)
    # Time the 4 agents actually occupied together: first start to last end.
    parallel_span_ms = round(max(a["end_ms"] for a in agents) - min(a["start_ms"] for a in agents), 1)
    # Everything the API returns to the UI.
    return {
        "question": question,
        "agents": agents,
        "synthesizer": result["synthesis"],
        "wall_clock_ms": wall_clock_ms,
        "sum_of_agents_ms": sum_of_agents_ms,
        "parallel_span_ms": parallel_span_ms,
    }
