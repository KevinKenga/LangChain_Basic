"""
similarity_search.py
=====================
STEP 1 of the "evolution from LangChain_100" plan: actually USE the
embeddings instead of just printing vectors.

What this script does:
1. Loads the document embeddings that embeddding_docs.py already saved to
   doc_embeddings.json (run embeddding_docs.py at least once first!).
2. Asks you for a query (type/paste text or pick a file - same style as the
   other scripts in this folder).
3. Embeds your query with the exact same model/dimensions used for the
   documents (text-embedding-3-small, 150 dims) - required for the
   comparison below to be meaningful.
4. Compares your query's vector to every saved document vector using
   cosine similarity, and prints the documents ranked from most to least
   similar.

Cosine similarity, in plain words: it measures how much two vectors point
in the same "direction" in embedding space. 1.0 = same meaning, 0 = unrelated,
negative = opposite meaning. It's the standard metric for comparing text
embeddings.
"""
import os
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")

from embedding_utils import get_text_from_user, cosine_similarity, load_embeddings

EMBEDDINGS_FILE = os.path.join(os.path.dirname(__file__), "doc_embeddings.json")

embedding = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=150,
    api_key=api_key,
)


def preview(text, length=100):
    """Show just the first part of a document, so long documents don't
    flood the terminal when we print results."""
    text = text.strip().replace("\n", " ")
    return text[:length] + ("..." if len(text) > length else "")


if __name__ == "__main__":
    if not os.path.exists(EMBEDDINGS_FILE):
        print(
            f"No {os.path.basename(EMBEDDINGS_FILE)} found yet.\n"
            "Run `python3 embeddding_docs.py` first to create and save some "
            "document embeddings, then come back and run this script."
        )
        raise SystemExit(1)

    stored_docs = load_embeddings(EMBEDDINGS_FILE)
    print(f"Loaded {len(stored_docs)} saved document(s) from {os.path.basename(EMBEDDINGS_FILE)}.")

    query_text = get_text_from_user(prompt_label="search query")
    query_vector = embedding.embed_query(query_text)

    # Score every stored document against the query, then sort best-first.
    scored = [
        (cosine_similarity(query_vector, doc["embedding"]), doc["text"])
        for doc in stored_docs
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    print("\nResults, most similar first:")
    for rank, (score, text) in enumerate(scored, start=1):
        print(f"{rank}. score={score:.4f}  {preview(text)}")
