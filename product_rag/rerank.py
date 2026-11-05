"""rerank.py - cross-encoder reranking of the agent's candidates."""
from sentence_transformers import CrossEncoder
import config

_model = None

def get_model() -> CrossEncoder:
    global _model
    if _model is None:                       # load once; it is ~90 MB
        _model = CrossEncoder(config.RERANK_MODEL)
    return _model

def dedupe(chunks: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for c in chunks:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    return unique

def rerank(question: str, chunks: list[dict], top_k: int = config.RERANK_TOP_K) -> list[dict]:
    chunks = dedupe(chunks)
    if not config.USE_RERANKER:
        # baseline for Question D1: just keep the highest embedding scores
        return sorted(chunks, key=lambda c: c["score"], reverse=True)[:top_k]
    if not chunks:
        return []

    by_embedding = sorted(chunks, key=lambda c: c["score"], reverse=True)
    scores = get_model().predict([(question, c["text"]) for c in by_embedding])
    scored = [{**c, "embed_rank": rank, "rerank_score": float(s)}
              for rank, (c, s) in enumerate(zip(by_embedding, scores), start=1)]
    scored.sort(key=lambda c: c["rerank_score"], reverse=True)
    for rank, c in enumerate(scored, start=1):
        c["rerank_rank"] = rank
        c["moved"] = c["embed_rank"] - rank
    return scored[:top_k]
