"""config.py - every setting lives here and nowhere else."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION = "flowdesk_docs"

# filename -> metadata attached to every chunk from that file
DOCUMENTS = {
    "01_FlowDesk_PRD_v3.0.pdf":                   {"doc_type": "prd",         "doc_date": "2026-07-22"},
    "02_FlowDesk_Pricing_and_Packaging_2026.pdf": {"doc_type": "pricing",     "doc_date": "2026-07-01"},
    "03_FlowDesk_Release_Notes_and_Roadmap.pdf":  {"doc_type": "releases",    "doc_date": "2026-10-02"},
    "04_Competitive_Analysis_Q1_2026.pdf":        {"doc_type": "competitive", "doc_date": "2026-03-10"},
    "05_Customer_Insights_Q3_2026.pdf":           {"doc_type": "insights",    "doc_date": "2026-10-05"},
}
DOC_TYPES = sorted({m["doc_type"] for m in DOCUMENTS.values()})

AGENT_MODEL = "gpt-4o-mini"        # research agent + generator
GUARD_MODEL = "gpt-4o-mini"        # classifiers: guardrail, grader
EMBED_MODEL = "text-embedding-3-small"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"   # local, ~90 MB first download

CHUNK_SIZE, CHUNK_OVERLAP = 800, 150
SEARCH_TOP_K = 8          # per tool call; the agent may call the tool several times
RERANK_TOP_K = 6          # chunks that reach the generator
MAX_TOOL_CALLS = 4        # ReAct safety limit per research round
MAX_RESEARCH_ROUNDS = 2   # grade -> retry loop limit
GROUNDING_THRESHOLD = 0.9 # share of numbers in the answer that must appear in context
USE_RERANKER = True       # flip to False for Question D1
