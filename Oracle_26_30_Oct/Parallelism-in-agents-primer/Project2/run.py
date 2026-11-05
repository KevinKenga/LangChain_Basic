"""Run the parallel voting demo: five judges, each with a different lens, classify
one email at the same time, then a tally node counts the votes and decides. The
summary at the end shows how the two reducers merged what the parallel judges made.
"""
import time
from collections import Counter

from graph import build_voting_graph, NUM_JUDGES
from sample_email import EMAIL

BAR = "=" * 60

if __name__ == "__main__":
    print(BAR)
    print(f" PARALLEL VOTING  —  {NUM_JUDGES} judges, each with a different lens")
    print(BAR)
    print("\nEmail under review:\n")
    print(EMAIL.strip())
    print("\nVotes coming in (in parallel):")

    graph = build_voting_graph()
    t0 = time.perf_counter()
    result = graph.invoke({"email": EMAIL, "votes": [], "total_confidence": 0})
    total = time.perf_counter() - t0

    records = result["votes"]
    counts = Counter(r["vote"] for r in records)
    avg_conf = result["total_confidence"] / len(records)

    print("\nHow the reducers merged the parallel writes:")
    print(f"   votes            (list reducer) -> {len(records)} separate records joined into 1 list")
    print(f"   total_confidence (sum reducer)  -> summed to {result['total_confidence']}  (avg {avg_conf:.0f}/100)")
    print(f"\n   tally: {dict(counts)}  ->  decision: {result['decision']}")

    print(BAR)
    top = counts.most_common(1)[0][1]
    print(f" FINAL DECISION: {result['decision']}   "
          f"({top} of {NUM_JUDGES} judges, avg confidence {avg_conf:.0f}/100)")
    print(f" took {total:.2f}s for all {NUM_JUDGES} judges together")
    print(BAR)