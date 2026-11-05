
# Agentic RAG — Product Management Assistant

The capstone of the parallelism series. It answers a real product-management
question from two PDFs, and it uses **everything from the earlier examples**:
parallel fan-out, a reducer that merges the parallel results, and fan-in — plus
one new idea, an **agentic self-check** that decides whether to answer or dig deeper.

## What it does

You ask one question. The system:

1. **expands** the question into three focused sub-queries;
2. **retrieves in parallel** — three retrievers search the PDFs at the same time;
3. **merges** their results with a reducer, then dedupes to a unique set of chunks;
4. **grades itself** — an LLM checks whether the retrieved context is actually
   enough to answer. If not, it runs one broader retrieval first;
5. **answers** — it writes a practical, structured answer using only what it found,
   and lists its sources.

The demo question spans **both** PDFs on purpose — "which features to build first"
(prioritisation) lives in one document, "how will I know if the launch worked"
(metrics) lives in the other — so you can see parallel retrieval genuinely pull
from two sources and the answer stitch them together.

## The flow

```
                 ┌──► retrieve_1 ─┐
   START ──► expand ──► retrieve_2 ─┼──► merge ──► grade ──► generate ──► END
                 └──► retrieve_3 ─┘                 │            ▲
                 (FAN-OUT: 3 at once)  (FAN-IN)     └─ broaden ──┘
                                                    (only if context is thin)
```

- **Fan-out** — `expand` points to three retrievers; they run in the same round.
- **Reducer** — each retriever appends its hits to the shared `chunks` box; the
  `add` reducer joins them into one list instead of letting them collide.
- **Fan-in** — `merge` waits for all three, then dedupes.
- **Agentic** — `grade` inspects its own retrieved context and decides the route:
  answer now, or `broaden` (one more retrieval) and then answer.

## How parallelism and reducers show up here (the payoff)

This is the same lesson from Examples 1 and 2, now doing real work:

- The three retrievers are a **fan-out**, exactly like the summarisers and the judges.
- `chunks: Annotated[list, add]` and `retrieval_log: Annotated[list, add]` are
  **reducers** — the reason three parallel retrievers can write to shared state at
  once. Remove one and the parallel retrieval crashes at the fan-in, just as before.
- `merge` is the **fan-in** — it only runs once all three retrievers finish.

## The files — you run only one

```
run.py                ← the ONLY file you run (pretty output lives here)
  └── graph.py               the agentic RAG workflow (fan-out, reducers, grade)
        ├── llm.py           OpenAI chat + embedding calls
        └── vectorstore.py   reads the PDFs, chunks, embeds, cosine search
docs/                        the knowledge source (two PDFs)
build_pdfs.py                one-off script that generated the two PDFs
```

| File               | Motive                      | What's inside                                                                                                                                                                          |
| ------------------ | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run.py`         | Launcher + presentation     | Runs the graph once and renders the report: query expansion, the parallel-retrieval table, the reducer-merge summary, the self-check, and the final answer                             |
| `graph.py`       | The workflow (the concept)  | `State` with **two reducers**, the `expand` / three `retrieve_*` / `merge` / `grade` / `broaden` / `generate` nodes, and the fan-out / fan-in / conditional wiring |
| `vectorstore.py` | Retrieval, kept transparent | Reads each PDF, splits into chunks, embeds them once, and does cosine-similarity search — no black box                                                                                |
| `llm.py`         | OpenAI calls, kept separate | Embeddings, query expansion, the grader, and the answer writer. Uses JSON responses so parsing never breaks                                                                            |
| `docs/*.pdf`     | The knowledge source        | Two practical PM guides: discovery + prioritisation, and metrics + launch                                                                                                              |
| `build_pdfs.py`  | Made the PDFs               | Run only if you want to regenerate them (needs`reportlab`)                                                                                                                           |

## How to run

```bash
pip3 install langgraph openai python-dotenv pypdf numpy rich
```

Create a `.env` file next to `run.py` (no quotes, no spaces):

```
OPENAI_API_KEY=sk-your-key-here
```

Then run just the one file:

```bash
python3 run.py
```

(The PDFs are already in `docs/`. You only need `reportlab` and `build_pdfs.py`
if you want to change the source documents.)

## What output to expect

A five-part report:

1. **Query expansion** — the one question shown as three sub-queries.
2. **Parallel retrieval** — a table with each retriever, its sub-query, how many
   hits it got, its top source PDF, and its time. Below it: "slowest branch Xs vs
   one-by-one they'd total Ys" — the parallel win, measured.
3. **Reducer merge** — e.g. "joined 12 hits into one list, dedupe left 7 unique
   chunks." That is the reducer doing its job on real data.
4. **Agentic self-check** — `SUFFICIENT` (answer now) or `INSUFFICIENT` (fetch more
   first), with the grader's one-line reason.
5. **Answer** — a clean, sectioned answer that pulls prioritisation from one PDF
   and launch metrics from the other, with the source PDFs listed.

## The one-line takeaways

- **Parallelism**: independent retrievers run at once; the group costs the slowest,
  not the sum.
- **Reducer**: the only reason parallel branches can write to one state box safely.
- **Fan-in**: the merge step waits for all branches before continuing.
- **Agentic**: the graph checks its own work and changes course — that judgement
  step is what separates *agentic* RAG from plain retrieve-then-answer.

## Where this goes next

This graph is the natural home for the two topics we set aside earlier:
a **human-in-the-loop** pause for approval before the final answer, and a
**guardrail** node that blocks off-topic or unsafe questions before retrieval.
Both slot into this same flow without changing the parallel core.
