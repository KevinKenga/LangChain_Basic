"""
=====================================================================
FILE: app/ingest.py
=====================================================================
PURPOSE
    Reads the 3 PDFs, cuts them into small chunks, turns each chunk
    into an embedding (a list of numbers), and keeps them in memory
    so agents can search them. This is the "R" (retrieve) in RAG.

WHAT PROBLEM IT SOLVES
    An LLM cannot read 3 whole PDFs for every question (slow, costly).
    We pre-compute embeddings once at server start; then each question
    only needs one embedding call plus a fast matrix multiplication.

HOW TO RUN
    Used by app/server.py at start-up. To test on its own:
        python -m app.ingest

EXPECTED OUTPUT
    Loaded 3 PDFs -> NN chunks
    then the top 3 chunks for a test question with their scores.
=====================================================================
"""

# dataclass auto-creates __init__ for simple "record" classes.
from dataclasses import dataclass

# numpy does the fast vector maths (cosine similarity).
import numpy as np

# OpenAI client, used here only for embeddings.
from openai import OpenAI

# PdfReader extracts text from each PDF page.
from pypdf import PdfReader

# Our settings (paths, chunk sizes, model names).
from app import config


@dataclass
class Chunk:
    """One small piece of a PDF."""
    # Unique id like "feedback-p2-c1" so the UI can show which chunk is which.
    chunk_id: str
    # Short source name: "feedback", "analytics" or "competitor".
    source: str
    # 1-based page number, used for citations.
    page: int
    # The chunk's text.
    text: str


def split_into_chunks(text: str) -> list[str]:
    """Cut page text into overlapping windows of CHUNK_WORDS words."""
    # Split on any whitespace to get a list of words.
    words = text.split()
    # How far the window moves each step (60 - 15 = 45 words).
    step = config.CHUNK_WORDS - config.CHUNK_OVERLAP
    # Collect chunk strings here.
    chunks = []
    # Start a window at 0, 45, 90, ... until we run out of words.
    for start in range(0, len(words), step):
        # Take CHUNK_WORDS words from this start position.
        window = words[start:start + config.CHUNK_WORDS]
        # Join the words back into one string and save it.
        chunks.append(" ".join(window))
        # Stop once this window reached the end of the page.
        if start + config.CHUNK_WORDS >= len(words):
            break
    # Return all chunks for this page.
    return chunks


def load_chunks() -> list[Chunk]:
    """Read every PDF and return a flat list of Chunk objects."""
    # All chunks from all PDFs go into this list.
    all_chunks = []
    # Loop over ("feedback", "customer_feedback_report.pdf"), etc.
    for source, filename in config.PDF_FILES.items():
        # Open the PDF file.
        reader = PdfReader(config.PDF_DIR / filename)
        # Loop over pages; start=1 so page numbers match what humans see.
        for page_num, page in enumerate(reader.pages, start=1):
            # Pull plain text from the page ("" if the page is empty).
            text = page.extract_text() or ""
            # Cut the page into chunks; enumerate gives chunk index.
            for i, piece in enumerate(split_into_chunks(text)):
                # Build the Chunk record and add it to the list.
                all_chunks.append(Chunk(f"{source}-p{page_num}-c{i}", source, page_num, piece))
    # Return every chunk.
    return all_chunks


class VectorStore:
    """Keeps chunks + their embeddings in memory and searches them."""

    def __init__(self, chunks: list[Chunk], client: OpenAI):
        # Save the chunk list; row i of the matrix belongs to chunks[i].
        self.chunks = chunks
        # Save the OpenAI client to embed questions later.
        self.client = client
        # Embed every chunk once, in a single batched API call.
        self.matrix = self._embed([c.text for c in chunks])

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Return a (len(texts), dim) matrix of unit-length embeddings."""
        # One API call for the whole list of texts.
        response = self.client.embeddings.create(model=config.EMBED_MODEL, input=texts)
        # Turn the list of embedding lists into a numpy matrix.
        vectors = np.array([item.embedding for item in response.data], dtype=np.float32)
        # Length (norm) of each row, kept 2-D so division broadcasts per row.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        # Divide each row by its length -> unit vectors, so dot product = cosine similarity.
        return vectors / norms

    def search(self, query: str, top_k: int, sources: list[str]) -> list[dict]:
        """Return the top_k chunks from the given sources, best first."""
        # Embed the question; [0] takes the single row out.
        q = self._embed([query])[0]
        # Cosine similarity of the question with EVERY chunk in one go.
        scores = self.matrix @ q
        # Indexes of chunks that belong to the allowed sources.
        allowed = [i for i, c in enumerate(self.chunks) if c.source in sources]
        # Sort allowed indexes by score, highest first, and keep top_k.
        best = sorted(allowed, key=lambda i: scores[i], reverse=True)[:top_k]
        # Build plain dicts so they can be sent as JSON to the UI later.
        return [
            {
                # Which chunk this is.
                "chunk_id": self.chunks[i].chunk_id,
                # Which PDF it came from.
                "source": self.chunks[i].source,
                # Which page, for citations.
                "page": self.chunks[i].page,
                # The text itself.
                "text": self.chunks[i].text,
                # Rank by vector search: 1 = best.
                "vector_rank": rank,
                # Cosine score rounded for display.
                "vector_score": round(float(scores[i]), 4),
            }
            # enumerate(start=1) gives rank 1, 2, 3 ...
            for rank, i in enumerate(best, start=1)
        ]


# Quick manual test: python -m app.ingest
if __name__ == "__main__":
    # Create the OpenAI client with our key.
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    # Read and chunk the PDFs.
    chunks = load_chunks()
    # Show how many chunks we got.
    print(f"Loaded {len(config.PDF_FILES)} PDFs -> {len(chunks)} chunks")
    # Build the in-memory vector store (one embedding API call).
    store = VectorStore(chunks, client)
    # Search all 3 sources with a test question.
    for hit in store.search("Should we build WhatsApp integration?", 3, list(config.PDF_FILES)):
        # Print rank, score, id and the first 80 characters.
        print(hit["vector_rank"], hit["vector_score"], hit["chunk_id"], hit["text"][:80])
