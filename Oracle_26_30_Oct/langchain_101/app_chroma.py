'''
FAST API backend on top of chroma db 

to run : uvicorn app_chroma:app --reload
Open : http://127.0.0.1:8000/docs

On first start the PDF is loaded, chunked and embedded into chroma_oracle_db.
Later starts reuse the stored chunks.

test query for /search: 
{
  "query": "What does the paper say about unsupervised pre training ? ",
  "top_k": 5
}

'''

import os
from fastapi import FastAPI # pip install fastapi # pip install uvicorn
from pydantic import BaseModel
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from dotenv import load_dotenv
load_dotenv(override=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # paths work from any directory
PDF_PATH = os.path.join(BASE_DIR, "gpt-1paper.pdf")
DB_DIR = os.path.join(BASE_DIR, "chroma_oracle_db")
COLLECTION = "gpt1paper"

embedding = OpenAIEmbeddings(model="text-embedding-3-small")


# define the vector store
vector_store = Chroma(
    collection_name = COLLECTION,
    embedding_function = embedding,
    persist_directory = DB_DIR
)

# ingest the PDF only if the collection is empty
if not vector_store.get(limit=1)["ids"]:
    print("Collection is empty, ingesting PDF ......")
    document_objects = PyPDFLoader(PDF_PATH).load()
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size = 300,
        chunk_overlap = 120
    )
    chunks = text_splitter.split_documents(document_objects)
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    vector_store.add_documents(chunks, ids = ids)
    print(f"Chunks stored in Chroma: {len(chunks)}")

app = FastAPI(title="GPT-1 paper search")

class SearchRequest(BaseModel):
    query: str
    top_k: int = 3  

@app.get("/chunks")
def list_chunks(limit : int=5):
    "Show the stored chunks with their id, text, embedding"
    stored = vector_store.get(limit=limit, include=["metadatas", "documents", "embeddings"])
    return [
        {
            "id": stored["ids"][i],
            "page": stored["metadatas"][i]["page"],
            "text": stored["documents"][i],
            "embedding_size": len(stored["embeddings"][i]),
            "embedding_first_5": [float(x) for x in stored["embeddings"][i][:5]],
        }
        for i in range(len(stored["ids"]))
    ]
 
@app.post("/search")
def search(request: SearchRequest):
    """Embed the query and return the k closest chunks. Lower distance = closer match."""
    results = vector_store.similarity_search_with_score(request.query, k=request.top_k)
    return [
        {
            "id": doc.id,
            "page": doc.metadata["page"],
            "distance": float(distance),
            "text": doc.page_content,
        }
        for doc, distance in results
    ]
 
