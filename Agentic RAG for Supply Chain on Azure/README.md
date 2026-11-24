# Agentic RAG for Supply Chain on Azure

Ask a question about a supply chain team's five documents and get an answer that
is checked before anyone sees it. The pipeline **decides which documents to
search**, **checks whether what it found is enough**, and if the answer can't be
verified it **pauses and asks a person** to approve, correct or reject it.

Use it from the **terminal** (`run_query.py`) or from a **web UI** (`UI/`) that
shows the router's plan, the grader's verdict, what each search found, how the
semantic ranker re-ordered it, and the final answer.

| Job                          | Service                                  |
| ---------------------------- | ---------------------------------------- |
| Store the PDFs               | Azure Blob Storage                       |
| Read the PDFs (text, tables) | PyMuPDF4LLM (free, runs locally)         |
| Store and search the chunks  | Azure AI Search (hybrid: keyword + vector) |
| Pick the best 5 chunks       | Azure AI Search semantic ranker          |
| Embeddings, answers, router, grader, checks | Azure OpenAI             |
| Steps, loop, review pause    | LangGraph                                |

PDFs are converted with **PyMuPDF4LLM** rather than Azure AI Document
Intelligence, which bills per page.

---

## The five documents

| File | `doc_type` | `fiscal_year` | What is inside |
| --- | --- | --- | --- |
| `sc_annual_review_fy2025.pdf` | `annual_review` | FY2025 | Yearly KPIs and narrative: OTIF, inventory, spend, lead times, freight, emissions, people |
| `sc_annual_review_fy2026.pdf` | `annual_review` | FY2026 | The same structure, one year later |
| `supplier_risk_register_fy2026.pdf` | `risk_register` | FY2026 | 12 critical suppliers: spend, single-source status, risk score, mitigation, CPO exceptions, scorecard band |
| `logistics_warehouse_report_fy2026.pdf` | `logistics_report` | FY2026 | Warehouses, utilisation, transport modes, 3PLs, freight cost by head, control tower |
| `procurement_policy_v3.pdf` | `procurement_policy` | FY2026 | Approval limits, bidding, onboarding, dual-sourcing rule, scorecard bands, payment terms, revision history |

`doc_type` + `fiscal_year` identify exactly one document, and that pair is what
a router plan step is made of.

---

## How it works, end to end

```
                         ┌───────────────────── INGESTION (once) ─────────────────────┐
 data/raw/*.pdf ──upload──► Blob Storage ──► PyMuPDF4LLM ──► data/processed/*.md
                                                                   │
                                                  chunks (800 chars, 120 overlap,
                                                  labelled doc_type + doc_title + fiscal_year)
                                                                   │
                                      Azure OpenAI embeddings (512 dims) ──► AI Search index
                         └────────────────────────────────────────────────────────────┘

                         ┌────────────────────── QUERY (every question) ──────────────┐
 question
   │
   ▼
 input guardrails ── refused? ──► polite refusal
   │  (personal data, sourcing decisions, off-topic)
   ▼
 ROUTER: intent + at most 3 searches (doc_type + fiscal_year) + one-line reason
   ▼
 retrieve: ONE filtered hybrid search per plan step ──► 20 candidates / search
   ▼
 rerank: semantic ranker keeps the best 5 / search
   ▼
 GRADER: enough evidence?
   ├── no, and attempts left ──► rewrite the query ──► retrieve again (2 attempts in total)
   └── yes, or no attempts left ──► generate
   ▼
 generate (gpt-4o): cited answer [1], [2] ... shaped for the intent
   ▼
 output guardrails: right shape for this intent? every figure traced to the right year?
   │
   ├── grounded ─────────────► answer shown
   └── can't verify ─────────► PAUSE → human approves / corrects / rejects
                         └────────────────────────────────────────────────────────────┘
```

Why every search is still filtered by **both** `doc_type` and `fiscal_year`: the
router picks the document, but the two annual reviews use almost identical
wording and print FY2025 next to FY2026 in the same table. An unfiltered search
mixes years. Q4 ("What was the average import lead time in FY2026?") is the
test: its FY2026 search must never return a chunk from the FY2025 review.

The graph, as LangGraph draws it (`python graph/build_graph.py --write` writes
`docs/graph.mmd`):

```
python graph/build_graph.py --write        # -> docs/graph.mmd, paste into mermaid.live
```

---

## What goes in, what comes out

**In:** a question.

**Out:** one of three things.
- **An answer** with citations, shaped for the intent: for `compare_years`, what
  FY2025 said, what FY2026 said, and what changed; for `lookup`, the direct
  answer then the detail; for `cross_document`, what each document says and how
  they fit together.
- **A refusal**, for off-topic questions, sourcing decisions ("should we
  terminate X"), or questions with personal data.
- **A pause for review**, when a figure or claim can't be traced to the right
  year's document.

---

## Setup (once)

### 1. Install

Python 3.11 or 3.12 is recommended.

```bash
cd "Agentic RAG for Supply Chain on Azure"
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create the Azure resources

Needs the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).

```bash
az login
bash azure_setup/provision.sh
```

It takes about 10 minutes and ends by printing a block of settings.
(Already have the resources? Skip this and fill `.env` by hand from the portal.)

### 3. Save the settings

```bash
cp .env.example .env
```

Paste the block that `provision.sh` printed into `.env`. Three values are easy to get wrong:

| Setting | Correct | Wrong |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | `https://<name>.openai.azure.com/` | `.../openai/v1` on the end → **404 Resource not found** |
| `AZURE_OPENAI_API_VERSION` | a REST API version, e.g. `2024-10-21` | a model version such as `2024-11-20` |
| `AZURE_STORAGE_CONNECTION_STRING` | the full string: `DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net` | the account key alone → **Connection string missing required connection details** |

`AZURE_OPENAI_FAST_DEPLOYMENT` is the small model the **router** and the
**grader** call. Leave it empty to reuse `AZURE_OPENAI_GUARDRAIL_DEPLOYMENT`.

`.env` holds keys and is git-ignored. Never commit it.

### 4. Put the five PDFs in `data/raw/`

```
data/raw/sc_annual_review_fy2025.pdf
data/raw/sc_annual_review_fy2026.pdf
data/raw/supplier_risk_register_fy2026.pdf
data/raw/logistics_warehouse_report_fy2026.pdf
data/raw/procurement_policy_v3.pdf
```

The names must match `DOCUMENTS` in `config.py`. `LOCAL_PDF_DIR` in `.env`
(default here: `./data/raw`) tells the uploader where to look. The PDFs are git-ignored.

### 5. Upload them, then build the index

```bash
python ingestion/upload_pdfs.py    # data/raw -> Blob Storage (container supply-chain-docs)
python run_ingestion.py            # PDFs -> markdown -> chunks -> embeddings -> AI Search
```

`run_ingestion.py` does three steps:

1. **PDF → markdown.** Converts each document with PyMuPDF4LLM and saves it to
   `data/processed/<doc_type>_<FY>.md`. Already-converted documents are read
   from there. A PDF missing from `data/raw/` is downloaded from Blob Storage first.
2. **Markdown → chunks.** 800 characters each, cut at headings and table rows
   where possible, every chunk labelled with its `doc_type`, `doc_title` and
   `fiscal_year`. The log prints a chunk count per document and a TOTAL line.
3. **Chunks → AI Search.** **Deletes and recreates** the `supply-chain` index,
   embeds every chunk (100 per call) and uploads them (500 per batch).

**Check it in the portal:** AI Search service → **Indexes → `supply-chain`**.
The document count must match the TOTAL chunk count from the ingestion log. In
**Search explorer**, JSON view:

```json
{
  "search": "*",
  "filter": "doc_type eq 'risk_register'",
  "select": "id,doc_type,doc_title,fiscal_year,position,text",
  "top": 5,
  "count": true
}
```

Only register chunks come back.

---

## Ask questions

### Option A: the web UI

```bash
python UI/server.py                # then open http://localhost:8000
python UI/server.py 8080           # another port
```

Type a question in the box at the top and press **Ask** (or ⌘/Ctrl + Enter). A
question takes about 10–30 seconds. The page shows:

- **Pipeline strip:** guardrails → router → hybrid search → semantic ranker →
  grader → generate → grounding → answer, each marked passed, flagged or failed.
- **Router plan and grader verdict:** the intent, one chip per planned search,
  how many retrieval attempts ran, the grader's verdict, the rewritten query if
  it retried, and the router's one-line reason.
- **Answer card:** the answer, a *grounded / needs review / ungrounded* badge,
  the share of figures that traced back to the sources, and anything flagged.
- **Human review:** if the answer can't be verified, the draft is shown with
  **Approve** / **Reject** buttons and a box for a corrected answer.
- **Retrieval, one tab per search (`annual_review · FY2025`, ...):**
  - *Before*: all 20 hybrid-search candidates with their scores; dropped ones greyed.
  - *How positions changed*: a slope chart from hybrid rank to semantic rank
    (green = promoted, red = demoted, dashed = dropped).
  - *After*: the 5 kept chunks with the semantic score (0–4), how many places
    each moved, its original hybrid rank, and its document title.
  - Hover any chunk to highlight it everywhere; click to read the full text.

`UI/server.py` uses only Python's standard library and calls the same
`build_graph()` as the terminal version. Paused reviews live in the server's
memory, so restarting it discards any unfinished review.

### Option B: the terminal

```bash
python run_query.py                                            # default question
python run_query.py "Who must approve a purchase order of 15 crore?"   # your question
```

If the answer needs review, the terminal asks you to approve (`a`) or reject (`r`)
and optionally type a corrected answer.

### Each step on its own

Every step also runs by itself:

```bash
python guardrails/safety.py        # what gets refused (free)
python guardrails/topic.py         # off-topic check (keyword: free; otherwise 1 embedding)
python guardrails/format.py        # badly shaped answers (free)
python guardrails/factual.py       # wrong-year figures caught (free)
python graph/router.py             # the free keyword fallback (no Azure call)
python graph/grader.py             # the free empty-search check (no Azure call)
python retrieval/search.py         # one filtered search per plan step
python retrieval/rerank.py         # what the semantic ranker changed
python graph/build_graph.py        # the pipeline as a Mermaid diagram
```

---

## Host it on Azure

The same web UI can run on **Azure App Service**. Visitors sign in with Microsoft
Entra ID first, and **Application Insights** times every request and every
graph step. In short:

```bash
# once: create Application Insights, an App Service plan and a web app, copy .env into its settings
# (every command, explained: hosting.md)

RESOURCE_GROUP=rg-supply-chain-rag APP_NAME=<your-web-app-name> bash azure_setup/deploy-app.sh
```

- `startup.sh` is how App Service starts the app (`python UI/server.py`, on `0.0.0.0:$PORT`).
- `GET /health` answers `{"status": "ok"}` for App Service's health check.
- With App Service sign-in switched on, the page shows **Signed in as ...** and a **Sign out** link.
- Monitoring is off unless `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, so local runs and tests are unaffected.

**Step by step, with every command: [hosting.md](hosting.md).**

---

## Key settings (`config.py`)

| Setting | Value | Meaning |
| --- | --- | --- |
| `EMBEDDING_DIMENSIONS` | `512` | Vector length requested from `text-embedding-3-small` (native 1,536). Smaller vectors use a third of the index storage. **Change it → re-run `run_ingestion.py`**, because the index and every vector must match. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Characters per chunk / repeated between neighbours |
| `MIN_CHUNK_LENGTH` | `100` | Shorter pieces (page numbers, stray headers) are dropped |
| `MAX_SEARCHES` | `3` | Most searches the router may plan |
| `MAX_RETRIEVAL_ATTEMPTS` | `2` | retrieve → grade → rewrite → retrieve, and no further |
| `VECTOR_SEARCH_TOP_K` | `20` | Candidates fetched per search by hybrid search |
| `RERANK_TOP_K` | `5` | Chunks kept per search after the semantic ranker |

### Why 800 characters, not 1,200

These five documents are short and table-heavy. A KPI table row is a line or
two, and the annual reviews print FY2025 next to FY2026 in the same table. At
1,200 characters a chunk swallows several rows -- and often both years' columns
-- so the retriever hands the model a chunk that mixes the year it asked for
with the year it must not use. At 800 characters a chunk usually holds one table
row or one short section, which keeps each figure beside its own label and its
own year. The overlap is cut from 200 to 120 for the same reason: less repeated
text means fewer chances for a neighbouring row to arrive with the wrong year.

---

## Tests

```bash
python -m pytest -q
```

All offline: no Azure account, no keys, no cost. Every Azure call is mocked.
They cover the router's fallback (with the OpenAI key removed), plan validation,
the grader's empty-search check, the retry loop stopping after 2 attempts, the
search filter for every plan step, citation stripping in the number check, the
guardrails (Q13–Q15 refused before any search), the review pause, the index
definition, the PDF-to-markdown cache, and hosting (`/health`, the signed-in
user, which host and port the server uses).

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `ValueError: Connection string missing required connection details` | `AZURE_STORAGE_CONNECTION_STRING` holds only the key. Paste the full connection string. |
| `openai.NotFoundError: 404 Resource not found` | Endpoint has `/openai/v1` on the end, the API version is wrong, or the deployment name in `.env` doesn't exist. |
| `data/processed/` is empty | Nothing is written there until `run_ingestion.py` finishes converting a document. |
| Vector dimension mismatch on upload or search | `EMBEDDING_DIMENSIONS` changed without rebuilding. Run `python run_ingestion.py`. |
| `WARNING: no semantic ranker scores` | Enable the semantic ranker on the AI Search service (Free plan is fine). |
| `pip` warns about `crewai-tools` / `pymupdf` | Another project in the same Python. Harmless here; use a `.venv` to keep them apart. |

---

## Cost: read before running

- **AI Search Basic** is billed **per hour** while it exists, even when idle.
- **PDF conversion is free.** PyMuPDF4LLM runs on your machine and caches results in `data/processed/`.
- **Azure OpenAI** is billed per token. Building the index embeds every chunk once;
  each question costs a few fast-model calls and one generation call.
- **Hosting (optional).** The App Service plan (B1) is billed per hour while it exists. See [hosting.md](hosting.md).

When you're done:

```bash
bash azure_setup/teardown.sh       # deletes everything, stops all charges
```

---

## Folder layout

```
config.py                 every setting (secrets come from .env)
azure_clients.py          one connection per Azure service
run_ingestion.py          build the search index
run_query.py              ask a question in the terminal, review if needed
telemetry.py              switches on Application Insights (off without a connection string)
startup.sh                how App Service starts the web app
hosting.md                host it on Azure: every command, end to end

data/                     git-ignored
  raw/                    the five PDFs
  processed/              markdown cache, one file per document

ingestion/
  upload_pdfs.py          PDFs -> Blob Storage
  load_pdfs.py            PDF -> PyMuPDF4LLM -> markdown (cached)
  chunk.py                markdown -> labelled chunks
  build_index.py          chunks -> embeddings -> Azure AI Search index

retrieval/
  search.py               one filtered hybrid + semantic search per plan step
  rerank.py               keep the 5 best by semantic score

guardrails/
  safety.py               input:  personal data? sourcing decision?
  topic.py                input:  about the supply chain documents?
  format.py               output: cites an extract, and compares both years when comparing
  factual.py              output: every figure in the right year's sources?

graph/
  state.py                what flows through
  router.py               decision 1: intent + plan, validated in Python, with a free fallback
  grader.py               decision 2: is the evidence enough?
  nodes.py                what each step does
  build_graph.py          the order, the retry loop, the pause for review, and each step's timing

UI/
  server.py               web server (laptop or App Service): runs the graph, /health, /api/me
  index.html              the page: query box, plan, answer, review, rerank chart, signed-in user

azure_setup/
  provision.sh            create every Azure resource
  teardown.sh             delete them all
  deploy-app.sh           zip the code and upload it to the web app

tests/                    offline tests
docs/graph.mmd            the Mermaid diagram of the compiled graph
```

---

## Model versions and regions

`provision.sh` deploys `gpt-4o` (2024-11-20), `gpt-4o-mini` (2024-07-18) and
`text-embedding-3-small` (1) with the `GlobalStandard` SKU in `eastus2`. Azure
retires model versions and quota varies by region. If a deployment fails, check
what your subscription offers in the Azure AI Foundry portal, then change
`LOCATION` or the versions at the top of the script.
