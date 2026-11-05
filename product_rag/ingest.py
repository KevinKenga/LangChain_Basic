"""ingest.py - PDF -> chunks (with metadata) -> Chroma. Run once."""
import os
import chromadb
import fitz                                    # PyMuPDF
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
import config

def split(text: str, size: int, overlap: int) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return [c.strip() for c in chunks if len(c.strip()) > 80]

def get_collection():
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    embed = OpenAIEmbeddingFunction(api_key=os.getenv("OPENAI_API_KEY"),
                                    model_name=config.EMBED_MODEL)
    return client.get_or_create_collection(config.COLLECTION, embedding_function=embed,
                                           metadata={"hnsw:space": "cosine"})

def main():
    col = get_collection()
    ids, docs, metas = [], [], []
    for filename, meta in config.DOCUMENTS.items():
        pdf = fitz.open(config.DATA_DIR / filename)
        for page_no, page in enumerate(pdf, start=1):
            for i, chunk in enumerate(split(page.get_text(), config.CHUNK_SIZE, config.CHUNK_OVERLAP)):
                ids.append(f"{meta['doc_type']}-p{page_no}-c{i}")
                docs.append(chunk)
                metas.append({**meta, "source": filename, "page": page_no})
    col.upsert(ids=ids, documents=docs, metadatas=metas)
    print(f"Indexed {len(ids)} chunks from {len(config.DOCUMENTS)} documents")

if __name__ == "__main__":
    main()
