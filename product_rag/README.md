# FlowDesk Product Assistant - Agentic RAG with LangGraph

Assignment 2 (Oracle bootcamp, 26-30 Oct). A LangGraph pipeline over five FlowDesk product PDFs:
input guardrail -> tool-calling research agent -> cross-encoder rerank -> context grader (retry loop)
-> generate -> output guardrail (PII mask, number grounding) -> human review (interrupt) -> answer.

## Setup (Python 3.10+)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
echo "OPENAI_API_KEY=<your-key>" > .env
python ingest.py
```

The versions in `requirements.txt` are pinned so they install on an Intel Mac (torch 2.2.2, pymupdf 1.28.2, numpy < 2).

## Run

```bash
python -m uvicorn api:app --reload          # web UI at http://localhost:8000
python main.py "What does the Growth plan cost?"   # CLI, prompts for review when needed
python main.py --auto-approve "..."                # CLI, batch mode
```

## Files

| File | Role |
|---|---|
| `config.py` | All settings |
| `ingest.py` | PDF -> chunks with metadata -> Chroma |
| `state.py` | Shared graph state |
| `tools.py` | `search_product_docs` tool with `doc_type` filter |
| `rerank.py` | Cross-encoder reranker (`USE_RERANKER` toggle) |
| `guardrails.py` | Input classifier, PII masking, number grounding |
| `agents.py` | Graph nodes |
| `pipeline.py` | Graph, retry loop, `interrupt_before=["human_review"]` |
| `main.py` | CLI with human review prompt |
| `api.py`, `ui/` | FastAPI streaming backend and browser UI |
