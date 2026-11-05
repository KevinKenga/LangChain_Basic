"""pipeline.py - wires the nodes into a LangGraph with a retry loop and an interrupt."""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
import config
from state import RAGState
from agents import (input_guardrail, research_agent, rerank_node, grade_context,
                    generate, output_guardrail, human_review, finalise)

def after_input(state: RAGState) -> str:
    return "allowed" if state["input_allowed"] else "blocked"

def after_grade(state: RAGState) -> str:
    if state.get("grade") == "INSUFFICIENT" and state.get("attempts", 0) < config.MAX_RESEARCH_ROUNDS:
        return "retry"
    return "answer"

def after_output(state: RAGState) -> str:
    return "needs_review" if state["needs_review"] else "passed"

def build_graph():
    g = StateGraph(RAGState)
    for name, fn in [("input_guardrail", input_guardrail), ("research_agent", research_agent),
                     ("rerank", rerank_node), ("grade_context", grade_context),
                     ("generate", generate), ("output_guardrail", output_guardrail),
                     ("human_review", human_review), ("finalise", finalise)]:
        g.add_node(name, fn)

    g.add_edge(START, "input_guardrail")
    g.add_conditional_edges("input_guardrail", after_input,
                            {"allowed": "research_agent", "blocked": END})
    g.add_edge("research_agent", "rerank")
    g.add_edge("rerank", "grade_context")

    g.add_conditional_edges("grade_context", after_grade,
                            {"retry": "research_agent", "answer": "generate"})
    g.add_edge("generate", "output_guardrail")
    g.add_conditional_edges("output_guardrail", after_output,
                            {"passed": "finalise", "needs_review": "human_review"})
    g.add_edge("finalise", END)
    g.add_edge("human_review", END)

    return g.compile(checkpointer=MemorySaver(), interrupt_before=["human_review"])
