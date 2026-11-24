"""
================================================================================
AZURE PIPELINE - EVERY SETTING IN ONE FILE
================================================================================

This is the agentic RAG pipeline for a supply chain team. It is a separate
project: it shares no code with the OpenAI/Chroma version, and nothing here
changes how that version runs.

Every Azure service the pipeline talks to is configured here:

    Azure OpenAI                     writes answers, embeds text, runs checks
    Azure AI Search                  stores the chunks, searches, reranks
    Azure Blob Storage               holds the PDFs in the cloud

PDFs are turned into markdown locally with PyMuPDF4LLM (free), not with
Azure Document Intelligence (billed per page -- too costly for these reports).

Secrets (keys, endpoints) are NOT written here. They are read from a .env file
in this folder. Copy .env.example to .env and fill it in -- or run
azure_setup/provision.sh, which prints the values for you.
================================================================================
"""

import os                                   # os.getenv reads environment variables
from pathlib import Path                    # Path builds file paths that work on every OS

from dotenv import load_dotenv              # load_dotenv copies .env values into the environment


# ==============================================================================
# SECTION 1 - FOLDERS
# ==============================================================================

PROJECT_ROOT = Path(__file__).parent                    # this folder: the project root

load_dotenv(PROJECT_ROOT / ".env", override=True)       # read .env; its values win over the shell's

DATA_DIR = PROJECT_ROOT / "data"                        # everything this pipeline writes lives under here
RAW_PDF_DIR = DATA_DIR / "raw"                          # PDFs downloaded from Blob Storage land here
PROCESSED_DIR = DATA_DIR / "processed"                  # markdown from PyMuPDF4LLM is cached here

# Where upload_pdfs.py finds the PDFs to send to Blob Storage. Put the five
# documents in data/raw/, or point LOCAL_PDF_DIR in .env at another folder.
LOCAL_PDF_DIR = Path(os.getenv("LOCAL_PDF_DIR", "data/raw")).expanduser()  # expanduser turns ~ into your home folder
if not LOCAL_PDF_DIR.is_absolute():                     # a relative path like ./data/raw...
    LOCAL_PDF_DIR = PROJECT_ROOT / LOCAL_PDF_DIR        # ...means relative to this folder, wherever you run from


# ==============================================================================
# SECTION 2 - THE DOCUMENTS
# ==============================================================================
# The five supply chain documents. Each entry is the file name (locally and in
# Blob Storage) plus the labels that every chunk of it carries into the search
# index:
#
#     doc_type     FILTERABLE -- which of the five documents this chunk is from
#     doc_title    returned with every hit, so a citation can name the document
#     fiscal_year  FILTERABLE -- the year the document covers
#
# doc_type + fiscal_year together identify exactly one document, and that pair
# is what a router plan step is made of.
# ==============================================================================

DOCUMENTS = [                                                   # one dictionary per source document
    {"filename": "sc_annual_review_fy2025.pdf",                 # file name, locally and in Blob Storage
     "doc_type": "annual_review",                               # which kind of document -- a search filter
     "doc_title": "Annual Review FY2025",                       # shown in citations
     "fiscal_year": "FY2025"},                                  # the year it covers -- a search filter
    {"filename": "sc_annual_review_fy2026.pdf",                 # the same review, one year later
     "doc_type": "annual_review",
     "doc_title": "Annual Review FY2026",
     "fiscal_year": "FY2026"},
    {"filename": "supplier_risk_register_fy2026.pdf",           # the twelve critical suppliers
     "doc_type": "risk_register",
     "doc_title": "Supplier Risk Register FY2026",
     "fiscal_year": "FY2026"},
    {"filename": "logistics_warehouse_report_fy2026.pdf",       # warehouses, transport, freight
     "doc_type": "logistics_report",
     "doc_title": "Logistics and Warehouse Report FY2026",
     "fiscal_year": "FY2026"},
    {"filename": "procurement_policy_v3.pdf",                   # approval limits, dual-sourcing rule
     "doc_type": "procurement_policy",
     "doc_title": "Procurement Policy v3",
     "fiscal_year": "FY2026"},
]

DOC_TYPES = sorted({doc["doc_type"] for doc in DOCUMENTS})        # the five document kinds, in order
FISCAL_YEARS = sorted({doc["fiscal_year"] for doc in DOCUMENTS})  # ["FY2025", "FY2026"]

# Every (doc_type, fiscal_year) pair that really exists. The router's plan is
# checked against this set, so a pair the model invented can never reach a
# search call.
VALID_PAIRS = {(doc["doc_type"], doc["fiscal_year"]) for doc in DOCUMENTS}


# ==============================================================================
# SECTION 3 - AZURE OPENAI
# ==============================================================================
# On Azure you do not call a model by its name. You first create a DEPLOYMENT of
# the model in your Azure OpenAI resource, give that deployment a name, and then
# call the deployment name. provision.sh names each deployment after its model,
# so the defaults below match what it creates.
# ==============================================================================

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")       # e.g. https://my-openai.openai.azure.com/
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")         # key 1 or key 2 from the resource's "Keys" page
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")  # REST API version the SDK speaks

GENERATION_DEPLOYMENT = os.getenv("AZURE_OPENAI_GENERATION_DEPLOYMENT", "gpt-4o")      # writes the cited answer
GUARDRAIL_DEPLOYMENT = os.getenv("AZURE_OPENAI_GUARDRAIL_DEPLOYMENT", "gpt-4o-mini")   # cheaper model for yes/no checks
EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")  # turns text into vectors

# The router and the grader both return a small JSON object, so they use the
# cheap "fast" deployment. AZURE_OPENAI_FAST_DEPLOYMENT lets you point that at
# whatever small model you actually deployed; with the setting empty it falls
# back to the guardrail deployment, so nothing has to change to get started.
FAST_DEPLOYMENT = os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT") or GUARDRAIL_DEPLOYMENT
ROUTER_DEPLOYMENT = FAST_DEPLOYMENT             # writes the plan: intent + searches
GRADER_DEPLOYMENT = FAST_DEPLOYMENT             # judges whether the evidence is enough

EMBEDDING_DIMENSIONS = 512                      # vector length we ask text-embedding-3-small for (native 1,536); the index must match


# ==============================================================================
# SECTION 4 - AZURE AI SEARCH
# ==============================================================================

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")       # e.g. https://my-search.search.windows.net
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY")         # an ADMIN key: we create the index and upload to it
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "supply-chain")  # name of the index we create

SEMANTIC_CONFIG_NAME = "supply-chain-semantic"  # name of the semantic ranker setup stored inside the index

VECTOR_SEARCH_TOP_K = 20                        # candidates fetched per search -- a wide net for the ranker to choose from
RERANK_TOP_K = 5                                # chunks kept per search after the semantic ranker re-scores them


# ==============================================================================
# SECTION 5 - BLOB STORAGE
# ==============================================================================

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")    # one string: account name + key
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "supply-chain-docs")  # container (folder) holding the PDFs

# Two more containers, used by the blob trigger (ingestion/process_blob.py):
#     MARKDOWN_CONTAINER   the markdown of every new PDF is written here
#     RESULTS_CONTAINER    the agent's answer about that PDF is written here
# They MUST be different from AZURE_STORAGE_CONTAINER. The blob trigger watches
# the PDF container, so writing the markdown back into it would fire the
# trigger again, on its own output, for ever.
MARKDOWN_CONTAINER = os.getenv("AZURE_MARKDOWN_CONTAINER", "supply-chain-markdown")  # markdown of each new PDF
RESULTS_CONTAINER = os.getenv("AZURE_RESULTS_CONTAINER", "supply-chain-results")     # the agent's answer about it


# ==============================================================================
# SECTION 6 - CHUNKING, THE AGENT'S LIMITS AND GUARDRAIL THRESHOLDS
# ==============================================================================
# CHUNK SIZE: smaller than the common 1,000-1,500 character default, on purpose.
# These five documents are short and table-heavy. A KPI table row is only a
# line or two, and the two annual reviews print FY2025 and FY2026 side by side
# in the same table. A 1,200-character chunk swallows several rows -- and often
# both years' columns -- so the retriever hands the model a chunk that mixes
# the year it asked for with the year it must not use. At 800 characters a
# chunk usually holds one table row or one short section, which keeps a figure
# next to its own label and its own year.
# ==============================================================================

CHUNK_SIZE = 800                                # characters per chunk: about one table row or one short section
CHUNK_OVERLAP = 120                             # characters repeated between neighbours so no sentence is cut in two
MIN_CHUNK_LENGTH = 100                          # anything shorter (page numbers, stray headers) is thrown away

MAX_SEARCHES = 3                                # the router may plan at most this many filtered searches
MAX_RETRIEVAL_ATTEMPTS = 2                      # retrieve -> grade -> rewrite -> retrieve: two attempts in total

TOPIC_SIMILARITY_THRESHOLD = 0.40               # how close a question must be to our examples to count as on-topic
GROUNDING_THRESHOLD = 0.90                      # share of an answer's numbers that must trace back to the sources
INTERRUPT_ON_LOW_GROUNDING = True               # False runs straight through without pausing for review


# ==============================================================================
# SECTION 7 - CHECKING THE SETTINGS
# ==============================================================================
# Failing early with a clear list is kinder than a confusing 401 error from deep
# inside an API call. Each Azure client calls require() with only the settings
# it needs, so a lesson that only uses Azure OpenAI works before the other
# services exist.
# ==============================================================================

def require(*names: str) -> None:
    """Stop with a clear message if any of the named settings is empty."""
    missing = [name for name in names if not globals().get(name)]   # look each name up among this file's settings
    if missing:                                                     # anything not filled in?
        raise RuntimeError(                                         # stop, saying exactly what to fix
            "These settings are missing from .env:\n  "
            + "\n  ".join(missing)                                  # one missing name per line
            + "\nCopy .env.example to .env, or run azure_setup/provision.sh."
        )
