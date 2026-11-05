# Parallel Agentic RAG with Re-ranking (LangGraph + FastAPI)

A teaching project. A product manager at **NimbusDesk** (a fictional helpdesk SaaS) asks *"Should we build this feature?"*. Four agents search three product-management PDFs **at the same time**, re-rank what they find, and a synthesizer writes one recommendation. The UI shows **how long each node took** and **how re-ranking changed the chunk order**.

Read `business_scenario.md` first for the business problem.

---

## 1. What happens when you click "Ask"

1. `static/index.html` sends `POST /ask` with `{"question": "..."}` to the FastAPI server.
2. `app/server.py` passes the question to the compiled LangGraph graph from `app/graph.py`.
3. The graph has four edges out of `START`, so LangGraph runs the 4 agent nodes **in the same step, each in its own thread**:

| Node | Task | PDFs searched |
|------|------|---------------|
| `customer_voice` | What customers ask for and complain about | `customer_feedback_report.pdf` |
| `usage_analytics` | What the numbers say (churn, adoption, response time) | `product_usage_analytics.pdf` |
| `market` | What competitors offer, deals we lost | `competitor_analysis.pdf` |
| `risk` | Risks, concerns, costs | all 3 |

4. Inside each agent node, three steps run in order, and each step is timed:
   - **Retrieve** (`app/ingest.py`): the question is embedded and compared with every chunk of that agent's PDFs using cosine similarity. The top **10** chunks come back.
   - **Re-rank** (`app/reranker.py`): a cross-encoder model reads the question and each of those 10 chunks **together** and gives each a new score. The list is sorted by that score and the top **3** are kept.
   - **Answer**: the LLM writes 3–4 bullet points from only those 3 chunks, citing `[source p.N]`.
5. The `synthesizer` node has an edge from all 4 agents, so it starts only after all 4 finish. It writes **Decision: Build now / Build later / Don't build**, the reasons, and the main risk.
6. `run_question()` adds the totals and FastAPI returns everything as JSON. The page draws it.

```
START ─┬─> customer_voice ──┐
       ├─> usage_analytics ─┤
       ├─> market ──────────┼─> synthesizer ─> END
       └─> risk ────────────┘
```

---

## 2. Why re-ranking is needed

Vector search turns the question into one list of numbers and each chunk into another list, then compares the lists. The question and the chunk are never read together, so a chunk can score high just because it shares words with the question.

The PDFs contain planted **keyword-trap** chunks to show this:

| Trap chunk | Where | Why it fools vector search |
|-----------|-------|----------------------------|
| Support team's weekend shifts are coordinated in a **WhatsApp** group | feedback p.2 | Says "WhatsApp", but it is about internal staffing |
| Staff attended an **AI** customer experience conference | feedback p.2 | Says "AI", "replies", but it is about travel |
| Newsletter email **replies** and open rates | analytics p.2 | Says "replies", but it is about marketing emails |
| Freshline ran a **WhatsApp** sticker campaign at Diwali | competitor p.2 | Says "WhatsApp", but it is a brand campaign, not a product feature |

The cross-encoder reads *"Customers keep asking for a WhatsApp integration — is it worth it?"* together with *"…shift swaps through a WhatsApp group…"* and scores it low, because the meaning does not match. In the UI table:

- **Vector #**: position after vector search
- **Re-rank #**: position after re-ranking
- **Move**: ▲ moved up, ▼ moved down
- Green rows were **kept** and sent to the LLM; faded rows were dropped.

The cost: re-ranking runs the model once per chunk, so it is slower than vector search. That is why we vector-search all chunks (cheap) and re-rank only 10 (accurate).

---

## 3. How to read the timeline

- Each bar starts at the node's `start_ms` and ends at its `end_ms`, measured from when the request began.
- The 4 agent bars **start within a few ms of each other and overlap**: this shows that they ran in parallel.
- The synthesizer bar starts only after the **last** agent bar ends: this shows the fan-in wait.
- Totals:
  - **4 agents ran in (parallel)**: first agent start → last agent end
  - **Sum of 4 agents (if sequential)**: what you would wait if they ran one after another
  - **Speed-up**: sum ÷ parallel. With 4 similar agents, expect about 3–4×.
- Each agent card splits its time into **retrieve + re-rank + LLM**. The LLM step is usually the largest. The re-rank step is the cost of better accuracy.

---

## 4. Project layout

```
parallel_agentic_rag/
├── business_scenario.md        # the business problem (read first)
├── README.md                   # this file
├── requirements.txt
├── .env.example                # copy to .env, add your OpenAI key
├── data/
│   ├── generate_pdfs.py        # creates the 3 synthetic PDFs
│   └── pdfs/                   # output PDFs land here
├── app/
│   ├── config.py               # all settings in one place
│   ├── ingest.py               # PDF -> chunks -> embeddings -> vector search
│   ├── reranker.py             # cross-encoder re-ranking
│   ├── graph.py                # LangGraph: 4 parallel agents + synthesizer + timing
│   └── server.py               # FastAPI: GET / and POST /ask
└── static/
    └── index.html              # UI: recommendation, timeline, re-rank tables
```

---

## 5. Run it

Requires Python 3.10+ and an OpenAI API key.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install packages
pip install -r requirements.txt

# 3. Add your key
cp .env.example .env               # then edit .env

# 4. Create the 3 PDFs
python data/generate_pdfs.py

# 5. (optional) Test each part on its own
python -m app.reranker             # trap chunk should score lower than real chunk
python -m app.ingest               # prints chunk count and top 3 vector hits

# 6. Start the server
uvicorn app.server:app --reload
```

Open http://127.0.0.1:8000 and click an example question.

The first start downloads the re-ranker model (about 90 MB) from Hugging Face. Later starts use the cached copy.

---

## 6. Things to try in class

1. **Turn re-ranking off**: in `app/graph.py`, replace the re-rank line with `reranked = [{**c, "rerank_score": 0, "rerank_rank": c["vector_rank"], "kept": c["vector_rank"] <= 3} for c in candidates]`. Ask the WhatsApp question and check whether a trap chunk now reaches the LLM.
2. **Make it sequential**: in `build_graph`, replace the 4 `START -> agent` edges with a chain `START -> customer_voice -> usage_analytics -> market -> risk -> synthesizer`. The timeline bars now line up end to end, and the wall-clock time is close to the sum. (The `agent_results` reducer still collects all 4.)
3. **Change the numbers** in `app/config.py`: set `RETRIEVE_TOP_K = 3`. Re-ranking now has nothing to choose from, so it cannot rescue a good chunk that vector search ranked 7th.
4. **Add a 5th agent**: add one dict to `AGENTS` in `app/graph.py`. The fan-out and fan-in edges are built from that list, so nothing else changes.

---

## 7. Success checks

| Check | Where to look |
|-------|---------------|
| Recommendation cites at least 2 PDFs with page numbers | Recommendation card |
| 4 agents start within a few ms | "Speed-up / start gap" box |
| Parallel time clearly below sum | Totals boxes |
| A chunk changes rank and a trap chunk is dropped | Re-rank tables (WhatsApp question, Customer Voice or Market agent) |
