"""
=====================================================================
FILE: app/server.py
=====================================================================
PURPOSE
    FastAPI web server. It:
      1. At start-up: loads the PDFs, builds the vector store, loads
         the re-ranker model and compiles the LangGraph graph.
      2. GET  /     -> sends the HTML UI (static/index.html).
      3. POST /ask  -> runs the question through the graph and returns
                       answers + timings + re-ranking tables as JSON.

WHAT PROBLEM IT SOLVES
    Connects the browser to the Python graph. Building everything once
    at start-up means each question only pays for search + LLM calls.

HOW TO RUN
    From the project root:
        uvicorn app.server:app --reload
    Then open http://127.0.0.1:8000

EXPECTED OUTPUT
    In the terminal:
        Startup: 3 PDFs -> NN chunks embedded, re-ranker loaded, graph ready
        Uvicorn running on http://127.0.0.1:8000
=====================================================================
"""

# asynccontextmanager lets us write the start-up/shut-down hook as one function.
from contextlib import asynccontextmanager

# FastAPI is the web framework; HTTPException returns clean error responses.
from fastapi import FastAPI, HTTPException

# FileResponse sends a file (our index.html) to the browser.
from fastapi.responses import FileResponse

# BaseModel validates the JSON body of POST /ask.
from pydantic import BaseModel

# run_in_threadpool runs our blocking graph call without freezing the server.
from starlette.concurrency import run_in_threadpool

# OpenAI client shared by embeddings and chat.
from openai import OpenAI

# Our modules.
from app import config
from app.graph import build_graph, run_question
from app.ingest import VectorStore, load_chunks
from app.reranker import Reranker


# Holds the compiled graph after start-up; a dict so the hook can fill it.
STATE = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts (before yield) and once when it stops (after)."""
    # Fail early with a clear message if the key is missing.
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
    # One OpenAI client for the whole app (it is safe to share across threads).
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    # Read and chunk the 3 PDFs.
    chunks = load_chunks()
    # Embed every chunk once and keep it in memory.
    store = VectorStore(chunks, client)
    # Load the cross-encoder model once.
    reranker = Reranker()
    # Build and save the graph.
    STATE["graph"] = build_graph(store, reranker, client)
    # Log the start-up summary.
    print(f"Startup: {len(config.PDF_FILES)} PDFs -> {len(chunks)} chunks embedded, re-ranker loaded, graph ready")
    # Hand control to FastAPI; the server now serves requests.
    yield
    # Nothing to clean up on shutdown.


# Create the FastAPI app and attach the start-up hook.
app = FastAPI(title="NimbusDesk Parallel Agentic RAG", lifespan=lifespan)


class AskRequest(BaseModel):
    """Shape of the JSON the UI sends: {"question": "..."}."""
    # The user's question.
    question: str


@app.get("/")
def index():
    """Send the HTML page."""
    # Return the UI file from the static folder.
    return FileResponse(config.STATIC_DIR / "index.html")


@app.post("/ask")
async def ask(req: AskRequest):
    """Run the question through the parallel graph."""
    # Remove spaces at the ends of the question.
    question = req.question.strip()
    # Reject empty questions.
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty.")
    # graph.invoke blocks for a few seconds, so run it in a worker thread
    # to keep the server free for other requests.
    return await run_in_threadpool(run_question, STATE["graph"], question)
