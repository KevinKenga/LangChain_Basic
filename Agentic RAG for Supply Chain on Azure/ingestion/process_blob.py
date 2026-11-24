"""
================================================================================
INGESTION STEP 4 - ONE NEW PDF: BLOB -> MARKDOWN -> INDEX -> ANSWER
================================================================================

WHAT THIS FILE DOES
-------------------
One function, process_blob(blob_name), takes the name of a PDF that is already
in Blob Storage and runs the whole pipeline on that one file:

    1. download it from the PDF container into a temporary folder
    2. convert it to markdown with PyMuPDF4LLM (the same analyse_pdf() the
       five course documents use)
    3. upload the markdown to a SECOND container, as <name>.md
    4. cut the markdown into chunks and upsert ONLY this document's chunks
       into the Azure AI Search index
    5. run the LangGraph agent on it and save the answer to a THIRD container,
       as <name>.answer.md

WHY THREE CONTAINERS
--------------------
    supply-chain-docs       the PDFs -- the blob trigger watches THIS one
    supply-chain-markdown   the markdown of each new PDF
    supply-chain-results    the agent's answer about each new PDF

The markdown must NOT go back into the PDF container: the trigger would see
its own output, run again, write another markdown, and never stop.

WHY A TEMPORARY FOLDER
----------------------
An Azure Function may only write inside /tmp. tempfile.TemporaryDirectory()
gives us a folder there (or anywhere else the code runs) and deletes it again
when the with-block ends, so nothing is left behind.

WHAT HAPPENS TO A DOCUMENT THE ROUTER DOES NOT KNOW
---------------------------------------------------
config.VALID_PAIRS is the router's only truth: a plan step whose
(doc_type, fiscal_year) pair is not in that set is dropped before any search
runs. An uploaded PDF therefore gets doc_type "uploaded", which is NOT in
VALID_PAIRS, so the router will never plan a search that reaches it. Its
chunks are still indexed and can be found by a direct search, and the agent
still runs (on the documents it does know). Fixing that properly means
teaching the router about uploaded documents, which is out of scope here --
so the limitation is reported in the returned dictionary instead.

HOW TO RUN (by hand, from the project folder)
---------------------------------------------
    python ingestion/process_blob.py new_supplier_audit_fy2027.pdf
    python ingestion/process_blob.py new_supplier_audit_fy2027.pdf --no-agent

The Azure Function in function_app/ calls the same function, so the trigger
and the command line do exactly the same work.
================================================================================
"""

import argparse                                 # reads the blob name and --no-agent from the command line
import json                                     # prints the result as JSON
import logging                                  # records failures in the function's log stream
import os                                       # os.getenv reads TRIGGER_QUESTION and the OpenAI endpoint
import re                                       # finds "fy2027" inside a file name
import sys                                      # sys.path lets us import from the folder above
import tempfile                                 # a temporary folder, deleted when the with-block ends
import uuid                                     # a unique thread id for each agent run
from datetime import datetime                   # the current year, for a file name with no year in it
from pathlib import Path                        # Path builds file paths and splits file names
from typing import Dict, List                   # type hints: what goes in and comes out

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # container names, index name, the five documents
from azure_clients import search_client, search_index_client  # the two Azure AI Search clients
from ingestion.build_index import (             # the existing index code, reused unchanged
    UPLOAD_BATCH_SIZE,                          # how many documents go up in one call
    build_index_definition,                     # the index definition, if the index does not exist yet
    embed_texts,                                # text -> 512 numbers, with Azure OpenAI
    to_search_document,                         # chunk + embedding -> the shape the index expects
)
from ingestion.chunk import chunk_document      # markdown -> labelled chunks
from ingestion.load_pdfs import analyse_pdf     # PDF -> markdown, with PyMuPDF4LLM

logger = logging.getLogger(__name__)            # one logger for this module; the function app shows its lines

DEFAULT_TRIGGER_QUESTION = "Summarise the key figures and risks in the newly uploaded document: {doc_title}"  # used when TRIGGER_QUESTION is empty


# ==============================================================================
# SECTION 1 - BLOB STORAGE: THE THREE CONTAINERS
# ==============================================================================

def blob_service():
    """The storage-account-level client: it can reach every container, not just the PDF one."""
    from azure.storage.blob import BlobServiceClient  # imported here, so loading this file needs no package

    config.require("AZURE_STORAGE_CONNECTION_STRING")  # stop early with a clear message if .env is incomplete
    return BlobServiceClient.from_connection_string(   # connect with account name + key in one string
        config.AZURE_STORAGE_CONNECTION_STRING
    )


def ensure_container(service, container_name: str) -> None:
    """Create a container if it is missing; do nothing if it already exists."""
    from azure.core.exceptions import ResourceExistsError  # raised when the container is already there

    container = service.get_container_client(container_name)  # point at this one container
    try:
        container.create_container()            # create it
    except ResourceExistsError:                 # already there?
        pass                                    # fine -- that is the normal case after the first run


def download_blob_to_temp(service, blob_name: str, temp_dir: str) -> Path:
    """Download one blob from the PDF container into the temporary folder and return its path."""
    container = service.get_container_client(config.AZURE_STORAGE_CONTAINER)  # the container the trigger watches
    blob = container.get_blob_client(blob_name)                # this one file inside it
    local_path = Path(temp_dir) / Path(blob_name).name         # keep only the file name: /tmp is flat enough
    local_path.write_bytes(blob.download_blob().readall())     # every byte, written to disk
    return local_path                           # where the PDF now sits


def upload_text(service, container_name: str, blob_name: str, text: str) -> str:
    """Write a text file into a container, creating the container first if needed. Returns the blob name."""
    ensure_container(service, container_name)   # the container may not exist on the first run
    container = service.get_container_client(container_name)  # point at it
    container.upload_blob(                      # write the file
        name=blob_name,                         # e.g. "new_supplier_audit_fy2027.md"
        data=text.encode("utf-8"),              # bytes, not a str
        overwrite=True,                         # a re-upload replaces the old copy
    )
    return blob_name                            # the caller records where it went


# ==============================================================================
# SECTION 2 - AZURE AI SEARCH: ONE DOCUMENT AT A TIME
# ==============================================================================

def ensure_index() -> bool:
    """Create the index only if it does not exist. Returns True if it was created."""
    client = search_index_client()              # the admin-side client
    if config.AZURE_SEARCH_INDEX in client.list_index_names():  # already there?
        return False                            # leave it alone: it holds the five documents' chunks
    client.create_index(build_index_definition())  # first run: create the same index build_index.py creates
    return True                                 # tell the caller a new, empty index was made


def upsert_chunks(chunks: List[Dict]) -> int:
    """Embed and upsert this document's chunks. Returns how many Azure accepted."""
    embeddings = embed_texts([chunk["text"] for chunk in chunks])  # one 512-number vector per chunk
    documents = [to_search_document(chunk, embedding)              # the shape the index expects
                 for chunk, embedding in zip(chunks, embeddings)]

    uploaded = 0                                # running count of successful uploads
    for start in range(0, len(documents), UPLOAD_BATCH_SIZE):  # 500 documents per call
        batch = documents[start:start + UPLOAD_BATCH_SIZE]     # the next 500
        results = search_client().upload_documents(documents=batch)  # upload_documents is an UPSERT: same id = replace
        uploaded += sum(1 for result in results if result.succeeded)  # count only what Azure accepted
    return uploaded                             # the caller reports this number

# WHY THERE IS NO "DELETE THE OLD CHUNKS FIRST" STEP
# --------------------------------------------------
# The chunk id is built from doc_type, fiscal_year and position
# ("uploaded_FY2027_3"), so a re-upload of the same file writes the same ids
# and Azure replaces those documents instead of adding duplicates. Deleting by
# source_file would need that field to be FILTERABLE, and in
# ingestion/build_index.py it is not -- and making it filterable means
# recreating the index, which this step must never do. One consequence: if a
# new version of a PDF has FEWER chunks than the old one, the extra old chunks
# stay in the index. Rebuilding with run_ingestion.py clears them.


# ==============================================================================
# SECTION 3 - METADATA: WHICH DOCUMENT IS THIS?
# ==============================================================================

def prettify_title(stem: str) -> str:
    """Turn a file name stem into a readable title: new_supplier_audit_fy2027 -> New Supplier Audit FY2027."""
    words = stem.replace("-", " ").replace("_", " ").split()  # split on underscores, dashes and spaces
    pretty = []                                 # the words, tidied, collect here
    for word in words:
        if word.lower().startswith("fy") and word[2:].isdigit():  # "fy2027" -> "FY2027"
            pretty.append("FY" + word[2:])
        else:                                   # any other word: capitalise its first letter
            pretty.append(word[:1].upper() + word[1:])
    return " ".join(pretty)                     # e.g. "New Supplier Audit FY2027"


def metadata_for(blob_name: str) -> Dict:
    """The labels this document's chunks carry: from config.DOCUMENTS, or inferred from the file name."""
    filename = Path(blob_name).name             # drop any folder part of the blob name
    for document in config.DOCUMENTS:           # one of the five documents we already know?
        if document["filename"] == filename:    # exact match on the file name
            return dict(document)               # reuse its labels unchanged

    stem = Path(filename).stem                  # e.g. "new_supplier_audit_fy2027"
    match = re.search(r"fy[\s_-]*(\d{4})", stem, re.IGNORECASE)  # a year written as fy2027, FY-2027 or fy 2027
    fiscal_year = f"FY{match.group(1)}" if match else f"FY{datetime.now().year}"  # a string, like the five documents
    return {                                    # an inferred entry, in the same shape as config.DOCUMENTS
        "filename": filename,                   # the file name as it sits in the container
        "doc_type": "uploaded",                 # NOT in config.VALID_PAIRS -- see the note at the top
        "doc_title": prettify_title(stem),      # shown in citations
        "fiscal_year": fiscal_year,             # a string, e.g. "FY2027"
    }


# ==============================================================================
# SECTION 4 - THE AGENT
# ==============================================================================

def trigger_question(doc_title: str) -> str:
    """The question the agent is asked about a new document; TRIGGER_QUESTION overrides the default."""
    template = os.getenv("TRIGGER_QUESTION") or DEFAULT_TRIGGER_QUESTION  # .env or app setting, else the default
    return template.replace("{doc_title}", doc_title)  # plain replacement: no format() surprises with braces


def citations_from(state: Dict) -> List[Dict]:
    """The chunks the answer was built from, without repeats."""
    seen = set()                                # (title, position) pairs already listed
    citations = []                              # results collect here
    for chunks in (state.get("reranked_chunks") or {}).values():  # one list per planned search
        for chunk in chunks:                    # best first
            key = (chunk.get("doc_title"), chunk.get("position"))  # one entry per chunk
            if key in seen:                     # already listed from another search?
                continue                        # skip it
            seen.add(key)                       # remember it
            citations.append({                  # a small, printable citation
                "doc_title": chunk.get("doc_title"),
                "doc_type": chunk.get("doc_type"),
                "fiscal_year": chunk.get("fiscal_year"),
                "position": chunk.get("position"),
            })
    return citations                            # every chunk the answer could have used


def ask_agent(question: str) -> Dict:
    """Run the whole LangGraph pipeline once and return what it decided and answered."""
    from graph.build_graph import build_graph       # imported here, so this module loads without langgraph
    from graph.state import create_initial_state    # a fresh state

    graph = build_graph()                       # the compiled pipeline, with its pause before human_review
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}  # a unique id, so the checkpointer can find this run

    state = graph.invoke(create_initial_state(question), thread)  # run until the end -- or until the pause

    paused = bool(graph.get_state(thread).next)  # True = the graph stopped before human_review
    answer = state.get("final_answer") or state.get("draft_answer") or ""  # what a person would see

    return {                                    # everything worth saving with the answer
        "question": question,
        "intent": state.get("intent"),
        "plan": state.get("plan") or [],
        "plan_reason": state.get("plan_reason"),
        "answer": answer,
        "draft_answer": state.get("draft_answer"),
        "grounding_verdict": state.get("grounding_verdict"),
        "grounding_score": state.get("grounding_score"),
        "paused": paused,                       # nothing was approved automatically
        "citations": citations_from(state),
    }


def answer_markdown(result: Dict, document: Dict) -> str:
    """The agent's result as one readable markdown file."""
    plan = ", ".join(f"{step['doc_type']} · {step['fiscal_year']}" for step in result.get("plan") or []) or "(none)"
    lines = [
        f"# {document['doc_title']} - agent answer",
        "",
        f"- Question: {result['question']}",
        f"- Router intent: {result.get('intent')}",
        f"- Plan: {plan}",
        f"- Grounding verdict: {result.get('grounding_verdict')} ({result.get('grounding_score') or 0:.2f})",
        f"- Paused for human review: {'yes' if result.get('paused') else 'no'}",
        "",
        "## Answer",
        "",
        result.get("answer") or "(no answer)",
    ]
    citations = result.get("citations") or []   # the chunks the answer was built from
    if citations:                               # only add the section when there is something in it
        lines += ["", "## Citations", ""]
        lines += [f"- {c['doc_title']} · chunk {c['position']}" for c in citations]
    return "\n".join(lines) + "\n"              # one trailing newline, like every other file here


# ==============================================================================
# SECTION 5 - THE WHOLE JOB FOR ONE BLOB
# ==============================================================================

def process_blob(blob_name: str, run_agent: bool = True) -> Dict:
    """Download, convert, upload the markdown, index the chunks, and optionally ask the agent.

    Returns a dictionary with:
        status          "ok", "partial" (ingestion worked, something after it did not),
                        "error" (nothing could be ingested) or "skipped" (not a PDF)
        blob            the blob name that was processed
        markdown_blob   the markdown file written to config.MARKDOWN_CONTAINER, or None
        chunks_indexed  how many chunks Azure AI Search accepted
        answer_blob     the answer file written to config.RESULTS_CONTAINER, or None
        errors          one readable line per failure
        notes           things worth knowing (the router limitation, a skipped agent, ...)
    """
    result = {                                  # the shape every caller sees, filled in as we go
        "status": "ok",
        "blob": blob_name,
        "markdown_blob": None,
        "chunks_indexed": 0,
        "answer_blob": None,
        "errors": [],
        "notes": [],
    }

    filename = Path(blob_name).name             # drop any folder part of the blob name
    if not filename.lower().endswith(".pdf"):   # only PDFs are converted
        result["status"] = "skipped"            # nothing was done, and nothing went wrong
        result["notes"].append("not a PDF: only .pdf files are processed")
        return result

    document = metadata_for(blob_name)          # the labels its chunks will carry
    result["document"] = document               # report them, so the caller can see what was inferred
    if document["doc_type"] not in config.DOC_TYPES:  # an inferred document, not one of the five
        result["notes"].append(
            "doc_type 'uploaded' is not in config.VALID_PAIRS, so the router will not plan a search "
            "for this document; its chunks are indexed, but a normal question will not reach them "
            "until the router knows the pair."
        )

    service = blob_service()                    # one storage client for all three containers

    with tempfile.TemporaryDirectory() as temp_dir:  # a folder that is deleted when the block ends
        try:
            pdf_path = download_blob_to_temp(service, blob_name, temp_dir)  # step 1: the PDF, on disk
        except Exception as exc:                # no file, no pipeline
            result["status"] = "error"
            result["errors"].append(f"download failed: {type(exc).__name__}: {exc}")
            logger.exception("download failed for %s", blob_name)
            return result

        try:
            markdown = analyse_pdf(pdf_path)    # step 2: PyMuPDF4LLM, free and local
        except Exception as exc:                # a scanned PDF with no text layer, or a broken file
            result["status"] = "error"
            result["errors"].append(f"conversion failed: {type(exc).__name__}: {exc}")
            logger.exception("conversion failed for %s", blob_name)
            return result

        try:                                    # step 3: the markdown, into its own container
            result["markdown_blob"] = upload_text(
                service, config.MARKDOWN_CONTAINER, f"{Path(filename).stem}.md", markdown
            )
        except Exception as exc:
            result["status"] = "partial"
            result["errors"].append(f"markdown upload failed: {type(exc).__name__}: {exc}")
            logger.exception("markdown upload failed for %s", blob_name)

    try:                                        # step 4: this document's chunks, into the index
        chunks = chunk_document({               # the same chunker the five documents use
            "text": markdown,
            "doc_type": document["doc_type"],
            "doc_title": document["doc_title"],
            "fiscal_year": document["fiscal_year"],
            "source_file": document["filename"],
        })
        ensure_index()                          # create the index only if it is missing
        result["chunks_indexed"] = upsert_chunks(chunks)  # upsert: same ids replace, never duplicate
    except Exception as exc:
        result["status"] = "partial"
        result["errors"].append(f"indexing failed: {type(exc).__name__}: {exc}")
        logger.exception("indexing failed for %s", blob_name)

    if not run_agent:                           # the caller asked for ingestion only
        result["agent_status"] = "skipped"
        return result

    if not os.getenv("AZURE_OPENAI_ENDPOINT"):  # no Azure OpenAI configured: the agent cannot run
        result["agent_status"] = "skipped"
        result["notes"].append("AZURE_OPENAI_ENDPOINT is not set, so the agent was not run")
        return result

    question = trigger_question(document["doc_title"])  # e.g. "Summarise the key figures ...: New Supplier Audit FY2027"
    try:                                        # step 5: the agent, on the whole index
        agent_result = ask_agent(question)
    except Exception as exc:                    # the agent must never undo the ingestion above
        result["agent_status"] = "failed"
        result["errors"].append(f"agent failed: {type(exc).__name__}: {exc}")
        logger.exception("agent failed for %s", blob_name)
        return result

    result["agent"] = agent_result              # the plan, the answer and the citations
    result["agent_status"] = "ok"
    try:                                        # the answer, into its own container
        result["answer_blob"] = upload_text(
            service, config.RESULTS_CONTAINER,
            f"{Path(filename).stem}.answer.md", answer_markdown(agent_result, document),
        )
    except Exception as exc:
        result["agent_status"] = "failed"
        result["errors"].append(f"answer upload failed: {type(exc).__name__}: {exc}")
        logger.exception("answer upload failed for %s", blob_name)

    return result                               # everything the caller needs to report


if __name__ == "__main__":                      # only when run directly
    parser = argparse.ArgumentParser(description="Process one PDF from Blob Storage: markdown, index, agent answer.")
    parser.add_argument("blob_name", help="the blob name inside the PDF container, e.g. new_supplier_audit_fy2027.pdf")
    parser.add_argument("--no-agent", action="store_true", help="ingest only: do not run the agent")
    args = parser.parse_args()                  # read the command line

    logging.basicConfig(level=logging.INFO)     # show this module's log lines on the console
    outcome = process_blob(args.blob_name, run_agent=not args.no_agent)  # the whole job
    print(json.dumps(outcome, indent=2, default=str))  # the result, readable, one key per line
    sys.exit(1 if outcome["status"] == "error" else 0)  # a failure code only when nothing was ingested
