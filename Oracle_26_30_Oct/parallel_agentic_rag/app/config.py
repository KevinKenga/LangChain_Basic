"""
=====================================================================
FILE: app/config.py
=====================================================================
PURPOSE
    One place for every setting the project uses: file paths, model
    names, API key, and the retrieval / re-ranking numbers.

WHAT PROBLEM IT SOLVES
    Without this file, values like "top 10 chunks" or the model name
    would be scattered across many files. Students change one number
    here and the whole system picks it up.

HOW TO RUN
    This file is not run directly. Other files do:
        from app import config

EXPECTED OUTPUT
    Nothing is printed. It only defines constants.
=====================================================================
"""

# os lets us read environment variables such as OPENAI_API_KEY.
import os

# Path gives OS-independent file paths.
from pathlib import Path

# load_dotenv reads the .env file and puts its values into os.environ.
from dotenv import load_dotenv


# Read .env (if present) so OPENAI_API_KEY becomes available below.
load_dotenv()

# Project root folder = parent of the "app" folder this file sits in.
BASE_DIR = Path(__file__).resolve().parent.parent

# Folder that holds the 3 PDFs created by data/generate_pdfs.py.
PDF_DIR = BASE_DIR / "data" / "pdfs"

# Folder that holds index.html for the UI.
STATIC_DIR = BASE_DIR / "static"

# The OpenAI key; empty string if not set, so we can show a clear error later.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Chat model used by every agent and the synthesizer. Small and cheap.
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Embedding model used for vector search (step 1 of retrieval).
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# Cross-encoder re-ranker (step 2). Runs locally on CPU, no API key needed.
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Short source names -> PDF file names. Agents filter chunks by these names.
PDF_FILES = {
    # Customer Success team's report.
    "feedback": "customer_feedback_report.pdf",
    # Data / Analytics team's report.
    "analytics": "product_usage_analytics.pdf",
    # Product Marketing team's report.
    "competitor": "competitor_analysis.pdf",
}

# Number of words in one chunk. Small chunks = more precise matches.
CHUNK_WORDS = 60

# Words shared between neighbouring chunks, so a sentence cut at a
# chunk edge still appears whole in one of the two chunks.
CHUNK_OVERLAP = 15

# How many chunks vector search returns BEFORE re-ranking.
RETRIEVE_TOP_K = 10

# How many chunks we keep AFTER re-ranking and send to the LLM.
RERANK_TOP_N = 3
