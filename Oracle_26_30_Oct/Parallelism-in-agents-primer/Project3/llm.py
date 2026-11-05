"""All OpenAI calls (chat + embeddings), kept apart from the graph logic.
Put your key in a .env file next to run.py:  OPENAI_API_KEY=sk-...
"""
from dotenv import load_dotenv
load_dotenv()  # reads the .env file and puts OPENAI_API_KEY into the environment

import json
from openai import OpenAI

client = OpenAI()  # picks up OPENAI_API_KEY from the environment
CHAT_MODEL = "gpt-4o"
EMBED_MODEL = "text-embedding-3-small"


def embed_texts(texts):
    """Embed a list of texts in ONE batched call. Returns a list of vectors."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def embed_query(text):
    """Embed a single query. Returns one vector."""
    return embed_texts([text])[0]


def expand_queries(question, n=3):
    """Rewrite the question into n focused sub-queries, each hitting a different
    angle. Asking for JSON keeps the parsing reliable (no fragile string splitting).
    """
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content":
                "You expand a product-management question into focused search queries. "
                f'Return JSON: {{"queries": [ ...{n} short queries... ]}}. '
                "Each query should target a different angle of the question."},
            {"role": "user", "content": question},
        ],
    )
    queries = json.loads(resp.choices[0].message.content).get("queries", [])[:n]
    while len(queries) < n:          # pad if the model returned fewer than asked
        queries.append(question)
    return queries


def grade_context(question, context):
    """The agentic self-check: is the retrieved context enough to answer well?
    Returns (verdict, reason) where verdict is 'sufficient' or 'insufficient'.
    """
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content":
                "You check whether the CONTEXT is enough to answer the QUESTION well. "
                'Return JSON: {"verdict": "sufficient" or "insufficient", '
                '"reason": "under 15 words"}.'},
            {"role": "user", "content": f"QUESTION:\n{question}\n\nCONTEXT:\n{context}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    verdict = "sufficient" if data.get("verdict") == "sufficient" else "insufficient"
    return verdict, data.get("reason", "")


def generate_answer(question, context):
    """Write the final answer using ONLY the retrieved context. Returns markdown."""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content":
                "You are a senior product manager. Answer the question using ONLY the "
                "context provided. Be concrete and practical. Structure the answer in "
                "markdown with short sections and action-oriented bullet points. If the "
                "context does not cover part of the question, say so briefly."},
            {"role": "user", "content": f"QUESTION:\n{question}\n\nCONTEXT:\n{context}"},
        ],
    )
    return resp.choices[0].message.content.strip()