"""
================================================================================
INGESTION STEP 2 - MARKDOWN TO LABELLED CHUNKS
================================================================================

A document is longer than we want to send to the model, so we cut it into small
pieces (CHUNKS) and later retrieve only the relevant ones.

Every chunk keeps the labels of the document it came from -- doc_type,
doc_title and fiscal_year. doc_type + fiscal_year is what lets Azure AI Search
look inside ONE document at a time. The two annual reviews use almost the same
wording, so without that filter the search cannot tell them apart.

WHY THE CHUNKS ARE SHORT (800 CHARACTERS)
-----------------------------------------
These documents are table-heavy. A KPI table row is a line or two, and the
annual reviews print FY2025 next to FY2026 in the same table. A long chunk
swallows several rows and often both years' columns, so the model receives a
figure from the wrong year in the same breath as the right one. At 800
characters a chunk usually holds one table row or one short section, which
keeps each figure beside its own label and its own year.

This step runs on your computer. No Azure service is involved.

HOW TO RUN
----------
    python ingestion/chunk.py
================================================================================
"""

import sys                                      # sys.path lets us import from the folder above
from pathlib import Path                        # Path builds file paths
from typing import Dict, List                   # type hints

from langchain_text_splitters import RecursiveCharacterTextSplitter  # cuts text at the most natural break it can find

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # chunk size, overlap, minimum length

# Where the splitter prefers to cut, best first. PyMuPDF4LLM writes
# markdown headings, so cutting at a heading keeps each section together.
MARKDOWN_SEPARATORS = [
    "\n# ",                                     # top-level heading  ("# Supplier Risk Register")
    "\n## ",                                    # sub-heading        ("## Dual-sourcing rule")
    "\n### ",                                   # sub-sub-heading
    "\n\n",                                     # blank line -- a paragraph break
    "\n",                                       # a single line break -- usually a table row
    ". ",                                       # the end of a sentence
    " ",                                        # a space between words
    "",                                         # anywhere at all -- the last resort
]


def build_splitter() -> RecursiveCharacterTextSplitter:
    """Create the splitter with our size, overlap and preferred cut points."""
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,           # aim for about 800 characters per chunk
        chunk_overlap=config.CHUNK_OVERLAP,     # repeat 120 characters between neighbours
        separators=MARKDOWN_SEPARATORS,         # try headings first, then rows, then sentences
        length_function=len,                    # measure size in characters
        is_separator_regex=False,               # the separators above are plain text, not patterns
    )


def chunk_document(loaded_document: Dict) -> List[Dict]:
    """Cut one document into chunks, each carrying the document's labels."""
    splitter = build_splitter()                 # a fresh splitter
    pieces = splitter.split_text(loaded_document["text"])  # the actual cutting

    chunks = []                                 # results collect here
    for position, text in enumerate(pieces):    # enumerate gives each piece its number: 0, 1, 2...
        text = text.strip()                     # remove spaces and blank lines at either end
        if len(text) < config.MIN_CHUNK_LENGTH: # too short to be useful (a page number, a lone heading)?
            continue                            # drop it
        chunks.append({                         # one chunk = text + labels
            "text": text,                                   # the content
            "doc_type": loaded_document["doc_type"],        # e.g. "risk_register" -- the search filter
            "doc_title": loaded_document["doc_title"],      # e.g. "Supplier Risk Register FY2026" -- citations
            "fiscal_year": loaded_document["fiscal_year"],  # e.g. "FY2026" -- the other search filter
            "source_file": loaded_document["source_file"],  # e.g. "supplier_risk_register_fy2026.pdf"
            "position": position,                           # where in the document it came from
        })
    return chunks                               # every usable chunk of this document


def chunk_all_documents(loaded_documents: List[Dict], verbose: bool = True) -> List[Dict]:
    """Chunk every document and return one combined list, logging a count per document."""
    all_chunks = []                             # results from every document
    for document in loaded_documents:           # one document at a time
        chunks = chunk_document(document)       # cut it up
        all_chunks.extend(chunks)               # add its chunks to the combined list
        if verbose:                             # print a count per document
            print(f"  {document['doc_type']:18} {document['fiscal_year']}  {len(chunks):>5} chunks")
    if verbose:                                 # and the total, which the index document count must match
        print(f"  {'TOTAL':18} {'':6}  {len(all_chunks):>5} chunks")
    return all_chunks                           # every chunk from every document


if __name__ == "__main__":                      # only when run directly
    from ingestion.load_pdfs import load_all_pdfs  # imported here: only needed for this demo

    chunk_all_documents(load_all_pdfs(verbose=False))  # load (from cache if possible), chunk, print counts
