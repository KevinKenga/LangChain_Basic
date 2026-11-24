"""
Offline tests for ingestion/process_blob.py and the Azure Function app.

Every test runs OFFLINE: Blob Storage, Azure AI Search and Azure OpenAI are
replaced with small fakes, and the agent is replaced with a stub, so no keys,
no resources and no money are needed.

Run from the project folder:
    python -m pytest tests/test_process_blob.py
"""

import sys                                      # sys.path decides where imports are looked up
from pathlib import Path                        # Path builds file paths
from types import SimpleNamespace               # a quick object with attributes, for fake results

import pytest                                   # the test runner
from azure.core.exceptions import ResourceExistsError  # what Blob Storage raises when a container exists

import config                                   # container names, the five documents
from ingestion import process_blob as process_blob_module  # the module under test
from ingestion.process_blob import metadata_for, prettify_title  # the two small helpers

PDF_NAME = "new_supplier_audit_fy2027.pdf"      # a file the five documents do not include
MARKDOWN = (                                    # long enough to survive MIN_CHUNK_LENGTH
    "# New Supplier Audit FY2027\n\n"
    "The audit covered twelve critical suppliers and found two single-source risks.\n\n"
    "## Key figures\n\n"
    "On-time delivery fell to 91.4 per cent, and freight cost rose by 6.2 per cent.\n"
)


# ------------------------------------------------------------------------------
# Fakes: Blob Storage, Azure AI Search, the index client
# ------------------------------------------------------------------------------

class FakeDownload:
    """What download_blob() returns: something with readall()."""
    def __init__(self, data):
        self._data = data

    def readall(self):
        return self._data


class FakeBlobClient:
    """One blob inside a fake container."""
    def __init__(self, service, name):
        self.service = service
        self.name = name

    def download_blob(self):
        return FakeDownload(self.service.blobs[self.name])


class FakeContainerClient:
    """One container: create it, upload into it, download from it."""
    def __init__(self, service, name):
        self.service = service
        self.name = name

    def get_blob_client(self, name):
        return FakeBlobClient(self.service, name)

    def create_container(self):
        if self.name in self.service.containers:            # already there?
            raise ResourceExistsError(f"{self.name} exists")  # the real SDK raises this too
        self.service.containers.add(self.name)

    def upload_blob(self, name, data, overwrite=False):
        self.service.uploads.append((self.name, name))       # remember where it went
        self.service.blobs[name] = data


class FakeBlobService:
    """The storage account: a few blobs, and a record of every upload."""
    def __init__(self, blobs):
        self.blobs = dict(blobs)
        self.containers = set()
        self.uploads = []                                    # [(container, blob name), ...]

    def get_container_client(self, name):
        return FakeContainerClient(self, name)


class FakeSearchClient:
    """The data-side search client: records every document it is given."""
    def __init__(self):
        self.uploaded = []

    def upload_documents(self, documents):
        self.uploaded.extend(documents)
        return [SimpleNamespace(succeeded=True) for _ in documents]


class FakeIndexClient:
    """The admin-side search client: an index that may or may not exist."""
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.created = []

    def list_index_names(self):
        return iter(self.existing)

    def create_index(self, index):
        self.created.append(index.name)
        return index


@pytest.fixture
def fakes(monkeypatch):
    """Replace every Azure call and the agent with a fake, and return the fakes."""
    service = FakeBlobService({PDF_NAME: b"%PDF-1.4 fake bytes"})   # the PDF the trigger would have seen
    search = FakeSearchClient()
    index = FakeIndexClient(existing=[config.AZURE_SEARCH_INDEX])   # the index already exists

    monkeypatch.setattr(process_blob_module, "blob_service", lambda: service)
    monkeypatch.setattr(process_blob_module, "analyse_pdf", lambda path: MARKDOWN)
    monkeypatch.setattr(process_blob_module, "embed_texts", lambda texts, verbose=True: [[0.0] * 4 for _ in texts])
    monkeypatch.setattr(process_blob_module, "search_client", lambda: search)
    monkeypatch.setattr(process_blob_module, "search_index_client", lambda: index)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")  # the agent is allowed to run
    monkeypatch.delenv("TRIGGER_QUESTION", raising=False)           # use the default question

    return SimpleNamespace(service=service, search=search, index=index)


def fake_agent(question):
    """A stand-in for ask_agent(): the shape the real one returns."""
    return {
        "question": question,
        "intent": "lookup",
        "plan": [{"doc_type": "annual_review", "fiscal_year": "FY2026"}],
        "plan_reason": "stub",
        "answer": "On-time delivery fell to 91.4 per cent.",
        "draft_answer": "On-time delivery fell to 91.4 per cent.",
        "grounding_verdict": "grounded",
        "grounding_score": 1.0,
        "paused": False,
        "citations": [{"doc_title": "Annual Review FY2026", "doc_type": "annual_review",
                       "fiscal_year": "FY2026", "position": 3}],
    }


# ------------------------------------------------------------------------------
# A file that is not a PDF is skipped before anything is touched
# ------------------------------------------------------------------------------

def test_non_pdf_is_skipped(monkeypatch):
    monkeypatch.setattr(process_blob_module, "blob_service", lambda: pytest.fail("storage was contacted"))
    result = process_blob_module.process_blob("notes.txt")
    assert result["status"] == "skipped"
    assert result["markdown_blob"] is None
    assert result["chunks_indexed"] == 0
    assert result["answer_blob"] is None


# ------------------------------------------------------------------------------
# A PDF: markdown into the markdown container, chunks into the index
# ------------------------------------------------------------------------------

def test_pdf_is_converted_uploaded_and_indexed(fakes):
    result = process_blob_module.process_blob(PDF_NAME, run_agent=False)

    assert result["status"] == "ok"
    assert result["markdown_blob"] == "new_supplier_audit_fy2027.md"
    assert ("supply-chain-markdown", "new_supplier_audit_fy2027.md") in fakes.service.uploads  # the markdown container
    assert all(container != config.AZURE_STORAGE_CONTAINER for container, _ in fakes.service.uploads)  # never the PDF one
    assert result["chunks_indexed"] > 0
    assert result["chunks_indexed"] == len(fakes.search.uploaded)      # every chunk reached the index
    assert {document["doc_type"] for document in fakes.search.uploaded} == {"uploaded"}  # inferred labels
    assert fakes.index.created == []                                   # an existing index is never recreated


def test_agent_answer_is_saved_in_the_results_container(fakes, monkeypatch):
    monkeypatch.setattr(process_blob_module, "ask_agent", fake_agent)
    result = process_blob_module.process_blob(PDF_NAME)

    assert result["agent_status"] == "ok"
    assert result["answer_blob"] == "new_supplier_audit_fy2027.answer.md"
    assert ("supply-chain-results", "new_supplier_audit_fy2027.answer.md") in fakes.service.uploads
    assert result["agent"]["grounding_verdict"] == "grounded"


# ------------------------------------------------------------------------------
# The agent can fail without undoing the ingestion
# ------------------------------------------------------------------------------

def test_agent_failure_does_not_break_ingestion(fakes, monkeypatch):
    def boom(question):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(process_blob_module, "ask_agent", boom)
    result = process_blob_module.process_blob(PDF_NAME)

    assert result["status"] == "ok"                    # the ingestion part still succeeded
    assert result["chunks_indexed"] > 0
    assert result["markdown_blob"] == "new_supplier_audit_fy2027.md"
    assert result["agent_status"] == "failed"
    assert any("agent failed" in error for error in result["errors"])
    assert result["answer_blob"] is None


def test_run_agent_false_skips_the_agent(fakes, monkeypatch):
    monkeypatch.setattr(process_blob_module, "ask_agent", lambda question: pytest.fail("the agent ran"))
    result = process_blob_module.process_blob(PDF_NAME, run_agent=False)

    assert result["agent_status"] == "skipped"
    assert result["answer_blob"] is None
    assert result["chunks_indexed"] > 0                # ingestion still happened


# ------------------------------------------------------------------------------
# Metadata: a known document, and one inferred from the file name
# ------------------------------------------------------------------------------

def test_metadata_for_a_known_document():
    meta = metadata_for("supplier_risk_register_fy2026.pdf")
    assert meta["doc_type"] == "risk_register"         # taken from config.DOCUMENTS
    assert meta["doc_title"] == "Supplier Risk Register FY2026"
    assert meta["fiscal_year"] == "FY2026"


def test_metadata_for_an_unknown_document():
    meta = metadata_for(PDF_NAME)
    assert meta["doc_type"] == "uploaded"              # not one of the five
    assert meta["doc_title"] == "New Supplier Audit FY2027"
    assert meta["fiscal_year"] == "FY2027"             # the number after "fy", as a string like the others


def test_prettify_title_keeps_the_year_upper_case():
    assert prettify_title("logistics-warehouse_report_fy2026") == "Logistics Warehouse Report FY2026"


# ------------------------------------------------------------------------------
# The function app: it imports, and registers both functions
# ------------------------------------------------------------------------------

def test_function_app_registers_both_functions():
    pytest.importorskip("azure.functions")             # skipped when the Functions SDK is not installed

    function_app_dir = str(Path(__file__).parent.parent / "function_app")
    sys.path.insert(0, function_app_dir)               # so "import function_app" finds function_app.py
    try:
        import function_app as function_app_module     # noqa: F401  the module under test
    finally:
        sys.path.remove(function_app_dir)              # leave sys.path as we found it

    names = {function.get_function_name() for function in function_app_module.app.get_functions()}
    assert names == {"on_new_pdf", "run_agent_manually"}
