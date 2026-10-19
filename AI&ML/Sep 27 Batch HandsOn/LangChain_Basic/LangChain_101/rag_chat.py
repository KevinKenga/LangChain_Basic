"""
rag_chat.py
============
STEP 4 of the "evolution from LangChain_100" plan - a minimal RAG
(Retrieval-Augmented Generation) pipeline. This is where everything else in
this folder connects together:

  embeddding_docs.py  -> creates + saves document embeddings (doc_embeddings.json)
  similarity_search.py -> proved we can find the closest document to a query
  chat_oi.py / chat_memory.py -> proved we can talk to a chat model

RAG = instead of letting the model answer from its own general training
data, we first RETRIEVE the most relevant document we have on disk, then
hand that document to the model as context and ask it to answer USING that
context. This is the same shape (just smaller) as the LangChainPDFExtract
project (NJ Transit PDFs -> OpenAI -> SQL Server).

Steps this script performs:
1. Load the saved document embeddings (run embeddding_docs.py first).
2. Ask you for a question.
3. Embed the question and find the single best-matching document with
   cosine similarity (same approach as similarity_search.py).
4. Build a prompt that includes that document's text as context, plus your
   question, and send it to the chat model.
5. Print the model's answer, which should be grounded in the retrieved
   document instead of just the model's general knowledge.
"""
import os
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
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
model = ChatOpenAI(model="gpt-4o", api_key=api_key)


def find_best_match(query_vector, stored_docs):
    """Return the text of the single document whose embedding is closest
    to the query's embedding (highest cosine similarity)."""
    best_score, best_text = -1.0, None
    for doc in stored_docs:
        score = cosine_similarity(query_vector, doc["embedding"])
        if score > best_score:
            best_score, best_text = score, doc["text"]
    return best_text, best_score


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

    question = get_text_from_user(prompt_label="question")
    question_vector = embedding.embed_query(question)

    context, score = find_best_match(question_vector, stored_docs)
    print(f"\nRetrieved context (similarity={score:.4f}):\n{context[:300]}...\n")

    messages = [
        SystemMessage(
            content=(
                "You are a helpful assistant. Answer the user's question using "
                "ONLY the context below. If the answer isn't in the context, say "
                "you don't have enough information.\n\n"
                f"Context:\n{context}"
            )
        ),
        HumanMessage(content=question),
    ]
    response = model.invoke(messages)
    print(f"AI: {response.content}")
