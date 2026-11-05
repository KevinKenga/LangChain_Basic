"""tools.py - retrieval exposed as a tool the research agent can call."""
from typing import Literal, Optional
from langchain_core.tools import tool
import config
from ingest import get_collection

_collection = get_collection()

DocType = Literal["prd", "pricing", "releases", "competitive", "insights"]

@tool
def search_product_docs(query: str, doc_type: Optional[DocType] = None) -> list[dict]:
    """Search FlowDesk's internal product documents.

    query: a short, specific search query (rewrite the user's question; do not paste it).
    doc_type: restrict to one document. prd = features/requirements/targets,
        pricing = plans/prices/discounts, releases = versions/dates/roadmap,
        competitive = competitors/win rates (dated March 2026, may be outdated),
        insights = customers/ARR/NPS/churn/feature requests. Leave empty to search all.
    """
    where = {"doc_type": doc_type} if doc_type else None

    res = _collection.query(query_texts=[query], n_results=config.SEARCH_TOP_K, where=where)

    ids = res["ids"][0] if res.get("ids") else []
    docs = res["documents"][0] if res.get("documents") else []
    metas = res["metadatas"][0] if res.get("metadatas") else []
    dists = res["distances"][0] if res.get("distances") else [0.0] * len(ids)
    return [{"id": i, "text": d, "doc_type": m.get("doc_type"), "doc_date": m.get("doc_date"),
             "page": m.get("page"), "score": round(1 - dist, 4)}
            for i, d, m, dist in zip(ids, docs, metas, dists)]
