"""Run the same work two ways and compare the timelines."""
import time

from graph import build_parallel_graph, build_linear_graph, reset_clock
from sample_docs import DOCUMENTS


BAR = "=" * 60


def run(graph, label: str):
    print(f"\n{BAR}\n {label}\n{BAR}")
    reset_clock()
    print(f"[ 0.00s]  dispatching {len(DOCUMENTS)} summarizer branches")
    t0 = time.perf_counter()
    result = graph.invoke({"documents": DOCUMENTS, "summaries": []})
    total = time.perf_counter() - t0
    print("-" * 60)
    print(f" TOTAL ({label.lower()}): {total:.2f}s")
    return total, result


if __name__ == "__main__":
    parallel_total, result = run(build_parallel_graph(), "PARALLEL")
    linear_total, _ = run(build_linear_graph(), "LINEAR")

    print(f"\n{BAR}")
    print(f" Parallel {parallel_total:.2f}s   vs   Linear {linear_total:.2f}s"
          f"   ->  {linear_total / parallel_total:.1f}x faster")
    print(BAR)

    print("\nCombined digest:\n")
    print(result["digest"])