"""
================================================================================
GRAPH PART 4 - THE WIRING (what runs in what order)
================================================================================

                    input_guardrail          safety, then topic
                          |
                +---------+---------+
             blocked              allowed
                |                    |
                |                  route        intent + at most 3 searches
                |                    |
                |                 retrieve      one filtered search per plan step
                |                    |
                |                  rerank       semantic ranker scores, 20 -> 5
                |                    |
                |                  grade        is the evidence enough?
                |                    |
                |          +---------+---------+
                |    insufficient            sufficient, or
                |    and attempts < 2        no attempts left
                |          |                    |
                |     (rewritten query)     generate     Azure OpenAI, cited answer
                |          |                    |
                |          +--> retrieve        output_guardrail  format, then grounding
                |                                   |
                |                         +---------+---------+
                |                     grounded            needs review
                |                         |                    |
                |                     finalise         [ GRAPH PAUSES ]
                |                         |                    |
                |                         |             human_review
                +-------------------------+---------+----------+
                                                    |
                                                   END

THE LOOP
--------
grade -> retrieve runs at most once, because retrieve_node counts its attempts
and route_after_grade only retries while attempts < MAX_RETRIEVAL_ATTEMPTS (2).
After the second attempt the graph generates whatever it has; the output
guardrails then decide whether a person must look at it.

THE PAUSE
---------
interrupt_before=["human_review"] makes LangGraph STOP just before that node and
return control to the caller, with the state saved by a CHECKPOINTER. Later the
caller writes the reviewer's decision into the state and resumes. Nothing sits
blocked while waiting -- the wait can be a second or a week.

HOW TO RUN
----------
    python graph/build_graph.py                  (prints the Mermaid diagram -- no Azure calls)
    python graph/build_graph.py --write          (writes it to docs/graph.mmd)
    python graph/build_graph.py --write out.mmd  (writes it somewhere else)
================================================================================
"""

import sys                                      # sys.path lets us import from the folder above
from pathlib import Path                        # Path builds file paths

from langgraph.checkpoint.memory import MemorySaver  # keeps paused runs in memory
from langgraph.graph import END, START, StateGraph   # the graph builder and its start/end markers

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # INTERRUPT_ON_LOW_GROUNDING, MAX_RETRIEVAL_ATTEMPTS
from graph.nodes import (                       # the nine steps
    finalise_node,
    generate_node,
    grade_node,
    human_review_node,
    input_guardrail_node,
    output_guardrail_node,
    rerank_node,
    retrieve_node,
    route_node,
)
from graph.state import GraphState              # the shape of the state
from guardrails.factual import GROUNDED         # the verdict that means "no review needed"
from telemetry import tracer                    # records each step in Application Insights (a no-op if monitoring is off)

DEFAULT_DIAGRAM_PATH = Path(__file__).parent.parent / "docs" / "graph.mmd"  # where --write puts the diagram


def traced(name: str, node):
    """Wrap one node so each run of it is recorded as a span called node.<name>, with its duration."""
    def run(state: GraphState) -> dict:         # LangGraph calls this instead of the node itself
        with tracer.start_as_current_span(f"node.{name}"):  # open a span; it closes, and records the time, when the node returns
            return node(state)                  # run the real node, unchanged, and hand back what it returned
    return run                                  # the wrapped node: same input, same output, plus a span


def route_after_input_guardrail(state: GraphState) -> str:
    """Read the state and name the next route. Changes nothing."""
    return "allowed" if state["input_allowed"] else "blocked"


def route_after_grade(state: GraphState) -> str:
    """Retry once with the rewritten query, or generate with what we have."""
    if state["grader_sufficient"]:              # enough evidence?
        return "generate"                       # write the answer
    if state.get("attempts", 0) < config.MAX_RETRIEVAL_ATTEMPTS:  # attempts left?
        return "retry"                          # search again with the rewritten query
    return "generate"                           # out of attempts: generate, and let the checks decide


def route_after_output_guardrail(state: GraphState) -> str:
    """Grounded answers finish; everything else goes to a person (unless review is switched off)."""
    if not config.INTERRUPT_ON_LOW_GROUNDING:   # review switched off in config?
        return "grounded"                       # treat everything as approved
    return "grounded" if state["grounding_verdict"] == GROUNDED else "needs_review"


def build_graph(enable_interrupt: bool = True, checkpointer=None):
    """Assemble the pipeline and return a runnable graph."""
    builder = StateGraph(GraphState)            # a graph whose state has GraphState's shape

    builder.add_node("input_guardrail", traced("input_guardrail", input_guardrail_node))  # register each step under a name
    builder.add_node("route", traced("route", route_node))                                # decision 1: which documents
    builder.add_node("retrieve", traced("retrieve", retrieve_node))                       # one filtered search per plan step
    builder.add_node("rerank", traced("rerank", rerank_node))                             # semantic ranker cut
    builder.add_node("grade", traced("grade", grade_node))                                # decision 2: enough evidence?
    builder.add_node("generate", traced("generate", generate_node))                       # the cited answer
    builder.add_node("output_guardrail", traced("output_guardrail", output_guardrail_node))  # format, then grounding
    builder.add_node("human_review", traced("human_review", human_review_node))           # apply the reviewer's decision
    builder.add_node("finalise", traced("finalise", finalise_node))                       # the grounded path

    builder.add_edge(START, "input_guardrail")  # every run starts with the input guardrail
    builder.add_conditional_edges(              # a fork: the route function picks the branch
        "input_guardrail",                      # after this node...
        route_after_input_guardrail,            # ...ask this function...
        {"allowed": "route", "blocked": END},   # ...and follow the matching branch
    )
    builder.add_edge("route", "retrieve")       # straight line: plan, then search
    builder.add_edge("retrieve", "rerank")      # retrieve -> rerank
    builder.add_edge("rerank", "grade")         # rerank -> grade
    builder.add_conditional_edges(              # the loop: retry once, or generate
        "grade",
        route_after_grade,
        {"retry": "retrieve", "generate": "generate"},
    )
    builder.add_edge("generate", "output_guardrail")  # generate -> output guardrail
    builder.add_conditional_edges(              # the second fork
        "output_guardrail",
        route_after_output_guardrail,
        {"grounded": "finalise", "needs_review": "human_review"},
    )
    builder.add_edge("finalise", END)           # both branches end the run
    builder.add_edge("human_review", END)

    return builder.compile(                     # turn the description into something runnable
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),  # where paused runs are saved
        interrupt_before=["human_review"] if enable_interrupt else [],             # THE PAUSE
    )


def mermaid_diagram() -> str:
    """The compiled graph as a Mermaid diagram -- paste it into https://mermaid.live for a picture."""
    return build_graph().get_graph().draw_mermaid()  # LangGraph draws its own nodes and edges


if __name__ == "__main__":                      # only when run directly
    diagram = mermaid_diagram()                 # no Azure call is made
    if "--write" in sys.argv:                   # write it to a file instead of printing it
        position = sys.argv.index("--write")    # where the flag sits on the command line
        target = Path(sys.argv[position + 1]) if len(sys.argv) > position + 1 else DEFAULT_DIAGRAM_PATH
        target.parent.mkdir(parents=True, exist_ok=True)  # create docs/ on the first run
        target.write_text(diagram + "\n", encoding="utf-8")  # one file, ready to paste into mermaid.live
        print(f"Wrote {target}")                # say where it went
    else:                                       # no flag: print it
        print(diagram)                          # paste the output into https://mermaid.live for a picture
