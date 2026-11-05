"""A tiny, transparent vector store: read the PDFs, split them into chunks, embed
the chunks, and find the closest ones to a query by cosine similarity. No black
box — this is the whole of 'retrieval' in about fifty lines, so students can see
exactly what a vector search does.
"""
import os
import numpy as np
from pypdf import PdfReader

from llm import embed_texts, embed_query


def _read_pdf(path):
    reader = PdfReader(path)
    return "\n".join(page.extract_text() for page in reader.pages)


def _chunk(text, source, target_chars=450):
    """Group the text into readable chunks of roughly target_chars each."""
    chunks, buffer = [], ""
    for line in (ln.strip() for ln in text.split("\n") if ln.strip()):
        if len(buffer) + len(line) > target_chars and buffer:
            chunks.append(buffer.strip())
            buffer = ""
        buffer += " " + line
    if buffer.strip():
        chunks.append(buffer.strip())
    return [{"id": f"{source}#{i}", "source": source, "text": c}
            for i, c in enumerate(chunks)]


class VectorStore:
    def __init__(self, chunks, vectors):
        self.chunks = chunks
        # store unit vectors so cosine similarity is just a dot product
        self.matrix = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    def search(self, query, k=4):
        """Return the k chunks most similar to the query, with a score each."""
        q = np.array(embed_query(query))
        q = q / np.linalg.norm(q)
        scores = self.matrix @ q
        top = np.argsort(scores)[::-1][:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in top]


def build_store(pdf_dir="docs"):
    """Read every PDF in pdf_dir, chunk it, embed all chunks in one call, and
    return a ready-to-search VectorStore."""
    chunks = []
    pdfs = sorted(f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf"))
    for name in pdfs:
        chunks += _chunk(_read_pdf(os.path.join(pdf_dir, name)), name)
    vectors = np.array(embed_texts([c["text"] for c in chunks]))
    print(f"Indexed {len(chunks)} chunks from {len(pdfs)} PDFs")
    return VectorStore(chunks, vectors)