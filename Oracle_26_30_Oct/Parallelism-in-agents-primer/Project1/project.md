
# Parallel Agents — Document Summarizer

A small LangGraph project that shows **how parallelism works** — and, just as
importantly, **when it does not help.**

## What this project does

We have three short documents. Three "summarizer" steps each summarize one
document, and a final "combine" step merges the three summaries into a single
digest.

We run the exact same work **two ways** and time both:

- **Parallel** — all three summaries run at the same time, then combine.
- **Linear** — the three summaries run one after another, then combine.

The program prints a timeline for each run so you can *see* the difference on
screen instead of just being told about it.

## The idea in one picture

```
                 ┌──► summarize doc 1 ─┐
   START ────────┼──► summarize doc 2 ─┼──► combine ──► END
                 └──► summarize doc 3 ─┘
   (split = fan-out)                   (join = fan-in)
```

- **Fan-out:** one start point splits into three branches that run together.
- **Fan-in:** the three branches come back together into one combine step.
- **Combine** can only run *after* all three summaries exist — it needs them as
  its input, so it can never be parallelized. This is an honest limit worth
  seeing.

## The files — you run only one

```
run.py                ← the ONLY file you run
  └── graph.py               the workflow (state, nodes, wiring)
        ├── llm.py           the GPT-4o calls
        └── sample_docs.py   the three documents
```

- **run.py** — fires the parallel run, then the linear run, and prints both timelines.
- **graph.py** — the state, the three summarizer nodes, the combine node, and two
  wirings of the same nodes (parallel vs linear).
- **llm.py** — the GPT-4o calls, kept separate so the credential setup stays out
  of the teaching code.
- **sample_docs.py** — three short, unrelated documents (no file reading needed).

## How to run

```bash
pip3 install langgraph openai python-dotenv
```

Create a `.env` file next to `run.py` with your key (no quotes, no spaces):

```
OPENAI_API_KEY=sk-your-key-here
```

Then run just the one file:

```bash
python3 run.py
```

## What to watch in the output

1. **The per-document times.** These are the same *kind* of work in both runs —
   parallelism does not make any single summary faster, it only lets them
   overlap.
2. **Combine.** It always runs last and on its own, because it depends on all
   three summaries. Parallelism can't touch it.
3. **The two TOTAL lines.** This is the real stopwatch time. Compare them.

## The lesson (read this carefully)

Parallelism is **not automatically faster.** It pays off only when three things
are all true:

- the tasks are genuinely **independent** (none needs another's result),
- each task is **slow / heavy enough** to be worth overlapping, and
- the system can actually **serve them at once** (enough rate limit, cores,
  bandwidth).

Remove any one of those and parallel can end up **slower** than linear. In this
demo the documents are tiny, so there is very little to overlap — and firing
three GPT calls at once can make each call slower due to contention on the API.
That is exactly when you should *not* reach for parallelism.

Rule of thumb: **draw the arrows first. If two steps don't feed each other, they
*can* run in parallel — but only bother when each step is genuinely slow.**
