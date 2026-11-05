"""The parallel voting workflow: state, the judge nodes, the tally node, and the wiring.

The five judges are NOT clones. Each looks at the same email through a different
lens (its persona), so they genuinely disagree — which is what makes an ensemble
vote worth taking. The prints inside the nodes are here only so the classroom can
SEE the votes arrive; in real code you would use logging instead.
"""
from collections import Counter
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

from llm import classify_email

# The panel: five judges, five different lenses. An ODD number of judges means a
# yes/no vote can never end in a tie.
JUDGES = [
    ("Strict filter",
        "You are a strict spam filter. Discount codes, deadlines, and 'act now' "
        "urgency are strong spam signals to you."),
    ("Personal reader",
        "You judge by human context. A named greeting, a real relationship, and a "
        "genuine-sounding message mean it is NOT spam to you."),
    ("Marketing lens",
        "You are a marketing analyst. A real business sending a legitimate "
        "promotion or discount is normal marketing, not spam."),
    ("Compliance eye",
        "You are a compliance officer. Any unsolicited discount code, time "
        "pressure, or opt-out style line reads as promotional spam."),
    ("Everyday user",
        "You are a regular email user. Judge on gut: would this annoy you in your "
        "inbox, or is it a message you'd actually welcome?"),
]
NUM_JUDGES = len(JUDGES)


# --- state -----------------------------------------------------------
# Both shared boxes below are written by all five judges in the SAME round,
# so both need a REDUCER to say how the many writes combine.
#
# The SAME reducer `add` (from the operator module) does two jobs, because it just
# combines two values of whatever type they are:
#     votes            (a list) -> add CONCATENATES:  [a] + [b] = [a, b]
#     total_confidence (an int) -> add SUMS:          70 + 80  = 150
# A reducer is nothing more than a "how to combine two values" function.
#
#   >>> WANT TO SEE THE CRASH? <<<
#   Change `votes` to a plain list (no reducer):  votes: list
#   Re-run, and LangGraph stops with:
#     InvalidUpdateError: At key 'votes': Can receive only one value per step.
#   Put the reducer back to fix it.
class State(TypedDict):
    email: str
    votes: Annotated[list, add]            # list reducer: collect every judge's record
    total_confidence: Annotated[int, add]  # sum reducer: add up every judge's confidence
    decision: str


# --- nodes -----------------------------------------------------------
def make_judge(name: str, persona: str):
    """Build one judge. It reads the email through its persona and returns its own
    vote, confidence, and reason. No judge sees any other judge's vote.
    """
    def judge(state: State) -> dict:
        vote, confidence, reason = classify_email(state["email"], persona)
        print(f"   {name:<15} -> {vote:<9} (conf {confidence:>3})  {reason}")
        return {
            "votes": [{"judge": name, "vote": vote, "confidence": confidence, "reason": reason}],
            "total_confidence": confidence,
        }
    return judge


def tally(state: State) -> dict:
    """Runs only after ALL judges finish. Picks the majority vote.
    Plain Python — a reminder that not every node needs an LLM.
    """
    counts = Counter(r["vote"] for r in state["votes"])
    winner = counts.most_common(1)[0][0]
    return {"decision": winner}


# --- wiring: fan-out to all judges, fan-in to tally ------------------
def build_voting_graph():
    g = StateGraph(State)
    g.add_node("tally", tally)

    for i, (name, persona) in enumerate(JUDGES, start=1):
        node_id = f"judge_{i}"
        g.add_node(node_id, make_judge(name, persona))
        g.add_edge(START, node_id)     # fan-out: every judge starts in the same round
        g.add_edge(node_id, "tally")   # fan-in: tally waits for every judge

    g.add_edge("tally", END)
    return g.compile()