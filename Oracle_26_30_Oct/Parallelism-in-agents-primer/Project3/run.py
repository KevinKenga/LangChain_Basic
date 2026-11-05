"""Run the agentic RAG and render a clean report of HOW it reached the answer:
the query expansion, the parallel retrieval, the reducer merge, the self-check,
and the final answer. All the pretty output lives here — the graph stays clean.
"""
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.markdown import Markdown
from rich import box

from graph import build_rag_graph

console = Console()

QUESTION = (
    "I'm planning the next release of our mobile app. How do I decide which "
    "features to build first, and how will I know after launch whether it worked?"
)


def main():
    graph = build_rag_graph()  # this line reads + embeds the PDFs

    console.print()
    console.rule("[bold cyan]Agentic RAG · Product Management Assistant[/]")
    console.print(Panel(QUESTION, title="Question", border_style="blue", box=box.ROUNDED))

    t0 = time.perf_counter()
    result = graph.invoke({"question": QUESTION, "chunks": [], "retrieval_log": []})
    total = time.perf_counter() - t0

    # 1 · Query expansion
    tree = Tree("[bold]Step 1 · Query expansion[/]   one question became three")
    for q in result["sub_queries"]:
        tree.add(f"[cyan]{q}[/]")
    console.print(tree)

    # 2 · Parallel retrieval
    log = sorted(result["retrieval_log"], key=lambda r: r["retriever"])
    table = Table(title="Step 2 · Parallel retrieval (3 retrievers at once)",
                  box=box.SIMPLE_HEAVY, title_style="bold", title_justify="left")
    table.add_column("Retriever")
    table.add_column("Sub-query", max_width=44)
    table.add_column("Hits", justify="right")
    table.add_column("Top source")
    table.add_column("Time", justify="right")
    for r in log:
        table.add_row(f"#{r['retriever']}", r["query"], str(r["hits"]),
                      r["top_source"], f"{r['seconds']:.2f}s")
    console.print(table)

    slowest = max(r["seconds"] for r in log)
    summed = sum(r["seconds"] for r in log)
    console.print(f"   [dim]ran in parallel: slowest branch {slowest:.2f}s · "
                  f"one-by-one they'd total {summed:.2f}s[/]")

    # 3 · Reducer merge (fan-in)
    console.print(Panel(
        f"the [bold]chunks[/] reducer joined [bold]{result['total_hits']}[/] hits from "
        f"3 retrievers into one list, then dedupe left [bold]{result['unique_hits']}[/] "
        f"unique chunks",
        title="Step 3 · Reducer merge (fan-in)", border_style="magenta", box=box.ROUNDED))

    # 4 · Agentic self-check
    verdict = result["grade"].upper()
    colour = "green" if verdict == "SUFFICIENT" else "yellow"
    line = f"[{colour}]{verdict}[/] — {result['grade_reason']}"
    if result.get("broadened"):
        line += "\n[yellow]→ context was thin, so it ran one broader retrieval before answering[/]"
    console.print(Panel(line, title="Step 4 · Agentic self-check",
                        border_style=colour, box=box.ROUNDED))

    # 5 · The answer
    console.print(Panel(Markdown(result["answer"]), title="Answer",
                        border_style="green", box=box.ROUNDED))
    console.print(f"[dim]Sources: {', '.join(result['sources'])}[/]")
    console.print(f"[dim]End-to-end: {total:.2f}s[/]\n")


if __name__ == "__main__":
    main()