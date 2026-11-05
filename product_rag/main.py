"""main.py - ask a question; if the graph pauses, act as the human reviewer.

Usage:
    python main.py "What does the Growth plan cost?"
    python main.py --auto-approve "..."      # batch mode, no prompt
"""
import argparse, uuid
from pipeline import build_graph

p = argparse.ArgumentParser()
p.add_argument("question")
p.add_argument("--auto-approve", action="store_true")
args = p.parse_args()

graph = build_graph()
cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}   # one thread per question
graph.invoke({"question": args.question, "attempts": 0, "candidates": [],
              "search_log": [], "steps": []}, cfg)

state = graph.get_state(cfg)
if state.next == ("human_review",):                       # the graph is paused
    v = state.values
    print("\n=== NEEDS HUMAN REVIEW ===")
    print("Why:", v["guardrail_report"])
    print("\nDraft:\n" + v["draft_answer"])
    if args.auto_approve:
        review = {"decision": "approve", "note": "batch"}
    else:
        d = input("\n[a]pprove / [e]dit / [r]eject? ").strip().lower()[:1]
        review = {"decision": {"a": "approve", "e": "edit"}.get(d, "reject"),
                  "note": input("Note for the log: ")}
        if review["decision"] == "edit":
            review["edited"] = input("Corrected answer: ")
    graph.update_state(cfg, {"review": review})            # write the decision into the paused state
    graph.invoke(None, cfg)                                # resume from where it stopped

final = graph.get_state(cfg).values
print("\n=== STEPS ===")
for s in final["steps"]:
    print("  ", s)
print("\n=== SEARCHES ===")
for q in final.get("search_log", []):
    print("  ", q)
print("\n=== ANSWER ===\n" + final["final_answer"])
