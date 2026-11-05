"""
=====================================================================
FILE: app/reranker.py
=====================================================================
PURPOSE
    Step 2 of retrieval: re-ranking. Takes the 10 chunks that vector
    search found and scores each one again with a cross-encoder model,
    then keeps only the best 3.

WHAT PROBLEM IT SOLVES
    Vector search embeds the question and each chunk SEPARATELY, then
    compares the two lists of numbers. It is fast, but it can be
    fooled by shared words: a paragraph about the support team's
    internal "WhatsApp group" looks close to a question about a
    "WhatsApp integration".
    A cross-encoder reads the question and the chunk TOGETHER, as one
    input, and outputs a single relevance score. It is slower (one
    model run per chunk) but much more accurate. So we use:
        vector search on ALL chunks  -> cheap, keeps 10
        cross-encoder on those 10    -> accurate, keeps 3

HOW TO RUN
    Used by app/graph.py. To test on its own:
        python -m app.reranker

EXPECTED OUTPUT
    The two test chunks with their re-rank scores; the product chunk
    scores higher than the internal-team chunk.
=====================================================================
"""

# CrossEncoder loads a model that scores (question, passage) pairs.
from sentence_transformers import CrossEncoder

# Our settings (model name, how many chunks to keep).
from app import config


class Reranker:
    """Wraps the cross-encoder model."""

    def __init__(self):
        # Download (first run only) and load the model into memory; ~90 MB.
        self.model = CrossEncoder(config.RERANK_MODEL)

    def rerank(self, query: str, candidates: list[dict], top_n: int) -> list[dict]:
        """Score every candidate, sort by the new score, mark the top_n as kept."""
        # Build (question, chunk text) pairs; the model reads each pair together.
        pairs = [(query, c["text"]) for c in candidates]
        # One score per pair. Higher = more relevant. Raw scores can be negative.
        scores = self.model.predict(pairs)
        # Copy each candidate and attach its new score, so we don't change the input list.
        scored = [{**c, "rerank_score": round(float(s), 4)} for c, s in zip(candidates, scores)]
        # Sort by the re-rank score, highest first.
        scored.sort(key=lambda c: c["rerank_score"], reverse=True)
        # Walk the sorted list to add the new rank and the kept flag.
        for new_rank, c in enumerate(scored, start=1):
            # New position after re-ranking (1 = best).
            c["rerank_rank"] = new_rank
            # Only the top_n chunks go to the LLM.
            c["kept"] = new_rank <= top_n
        # Return all 10 (the UI shows the dropped ones too, for teaching).
        return scored


# Quick manual test: python -m app.reranker
if __name__ == "__main__":
    # Load the model.
    rr = Reranker()
    # Two fake candidates: one relevant, one keyword trap.
    demo = [
        # Trap: says WhatsApp but is about internal staff shifts.
        {"chunk_id": "trap", "text": "The Customer Success team coordinates weekend shift swaps through a WhatsApp group."},
        # Relevant: about customers wanting the product feature.
        {"chunk_id": "real", "text": "164 respondents requested a WhatsApp integration so their buyers' chats are tracked in NimbusDesk."},
    ]
    # Re-rank and keep the top 1.
    for c in rr.rerank("Should we build a WhatsApp integration for customers?", demo, 1):
        # Print id, score, new rank and kept flag.
        print(c["chunk_id"], c["rerank_score"], c["rerank_rank"], c["kept"])
