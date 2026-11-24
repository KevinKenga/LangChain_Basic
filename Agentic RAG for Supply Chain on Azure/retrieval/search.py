"""
================================================================================
RETRIEVAL STEP 1 - PLAN-DRIVEN HYBRID SEARCH IN AZURE AI SEARCH
================================================================================

WHAT THIS FILE DOES
-------------------
Takes the question and the router's PLAN -- a short list of (doc_type,
fiscal_year) pairs -- and runs ONE filtered hybrid + semantic search per step.
The results come back keyed by the search that produced them:

    {"annual_review · FY2025": [...], "annual_review · FY2026": [...]}

so the UI can show one tab per search, and the grader can say which search came
back empty.

THAT ONE CALL DOES THREE THINGS
-------------------------------
    1. KEYWORD search   (BM25)  finds chunks containing the question's words
    2. VECTOR search            finds chunks whose MEANING is close to the question
    3. SEMANTIC ranker          Azure's reranking model reads the question and each
                                candidate TOGETHER and gives it a new score

Keyword + vector together is called HYBRID search. Azure merges the two lists
with a method called Reciprocal Rank Fusion: a chunk ranked high in either list
ends up high in the merged list.

The semantic ranker's scores come back on the same results. We keep both
scores, so the next step (rerank.py) can show what the semantic ranker changed.

WHY EVERY SEARCH IS STILL FILTERED BY fiscal_year
-------------------------------------------------
The router already picked the document. That is not enough. The two annual
reviews use almost the same wording, and their KPI tables print FY2025 next to
FY2026. Neither keyword nor vector search can tell "import lead time was X" in
one year from "import lead time was Y" in the other -- both look like an
excellent match. Hybrid search does not fix that.

The fix is a FILTER on BOTH labels, so a search can never see a chunk from
another document or another year. Azure writes filters in OData:

    doc_type eq 'annual_review' and fiscal_year eq 'FY2026'

Q4 ("What was the average import lead time in FY2026?") is the test: its
FY2026 search must never return a chunk from the FY2025 review.

HOW TO RUN
----------
    python retrieval/search.py
================================================================================
"""

import sys                                      # sys.path lets us import from the folder above
from pathlib import Path                        # Path builds file paths
from typing import Dict, List, Optional         # type hints

sys.path.insert(0, str(Path(__file__).parent.parent))  # make the project folder importable

import config                                   # top-k, deployment names, semantic config name
from azure_clients import openai_client, search_client  # Azure OpenAI for the embedding, Search for the query

SEARCH_KEY_SEPARATOR = " · "                    # "annual_review · FY2025": readable, and unique per search


def embed_question(question: str) -> List[float]:
    """Turn the question into an embedding -- with the SAME deployment used for the chunks."""
    response = openai_client().embeddings.create(  # one call to Azure OpenAI
        model=config.EMBEDDING_DEPLOYMENT,      # must match ingestion, or the numbers are not comparable
        input=[question],                       # a list with one text in it
        dimensions=config.EMBEDDING_DIMENSIONS, # same length as the indexed vectors
    )
    return response.data[0].embedding           # the EMBEDDING_DIMENSIONS numbers for the question


def odata_quote(value: str) -> str:
    """Wrap a value in single quotes for OData, doubling any quote inside it (O'Brien -> 'O''Brien')."""
    return "'" + value.replace("'", "''") + "'"  # OData's escaping rule: a quote inside text is written twice


def build_filter(doc_type: Optional[str] = None, fiscal_year: Optional[str] = None) -> Optional[str]:
    """Build an OData filter such as: doc_type eq 'annual_review' and fiscal_year eq 'FY2026'."""
    conditions = []                             # each condition is one "field eq 'value'" piece
    if doc_type:                                # a document kind was given?
        conditions.append(f"doc_type eq {odata_quote(doc_type)}")        # keep only that document's chunks
    if fiscal_year:                             # a year was given?
        conditions.append(f"fiscal_year eq {odata_quote(fiscal_year)}")  # keep only that year's chunks
    return " and ".join(conditions) or None     # join with "and"; no conditions means no filter at all


def search_key(doc_type: str, fiscal_year: str) -> str:
    """The key one search's results are stored under, e.g. 'annual_review · FY2025'."""
    return f"{doc_type}{SEARCH_KEY_SEPARATOR}{fiscal_year}"


def to_result(hit: Dict) -> Dict:
    """Turn one Azure search hit into the plain dictionary the rest of the pipeline uses."""
    return {
        "text": hit["text"],                    # the chunk's content
        "doc_type": hit["doc_type"],            # which document it came from
        "doc_title": hit["doc_title"],          # the document's title, for citations
        "fiscal_year": hit["fiscal_year"],      # its year
        "position": hit["position"],            # where in the document it came from
        "score": hit["@search.score"],          # the HYBRID score (keyword + vector, merged)
        "reranker_score": hit.get("@search.reranker_score"),  # the SEMANTIC ranker's score, 0 to 4; None if unavailable
    }


def search(question: str, doc_type: Optional[str] = None, fiscal_year: Optional[str] = None,
           top_k: Optional[int] = None) -> List[Dict]:
    """Hybrid search plus semantic ranking. Returns candidates in HYBRID order (before reranking)."""
    from azure.search.documents.models import VectorizedQuery  # describes the vector half of the search

    top_k = top_k or config.VECTOR_SEARCH_TOP_K  # read the config now, not when the function was defined

    hits = search_client().search(              # ONE call to Azure AI Search
        search_text=question,                   # the keyword half: BM25 over the "text" field
        vector_queries=[VectorizedQuery(        # the vector half
            vector=embed_question(question),    # the question's embedding
            k_nearest_neighbors=top_k,          # how many nearest chunks the vector search contributes
            fields="embedding",                 # which field holds the vectors
        )],
        filter=build_filter(doc_type, fiscal_year),  # stay inside one document and one year
        query_type="semantic",                  # also run the semantic ranker over the merged results
        semantic_configuration_name=config.SEMANTIC_CONFIG_NAME,  # the ranker setup stored in the index
        top=top_k,                              # return this many results in total
        select=["text", "doc_type", "doc_title", "fiscal_year", "position"],  # fields to return (not the vector)
    )

    results = [to_result(hit) for hit in hits]  # convert every hit to our plain shape

    # Azure returns results in the SEMANTIC ranker's order. We put them back into
    # the hybrid order, so this step shows what search alone found, and the next
    # step (rerank.py) can show what the semantic ranker changed.
    results.sort(key=lambda r: r["score"], reverse=True)  # highest hybrid score first
    return results                              # up to top_k candidates


def search_plan(question: str, plan: List[Dict]) -> Dict[str, List[Dict]]:
    """Run ONE filtered search per plan step, keyed by that step, e.g. 'annual_review · FY2025'."""
    return {                                    # one entry per planned search, in plan order
        search_key(step["doc_type"], step["fiscal_year"]): search(  # one filtered search per step
            question,                           # the question (or the grader's rewritten query)
            doc_type=step["doc_type"],          # which document
            fiscal_year=step["fiscal_year"],    # which year -- never both years in one search
        )
        for step in plan                            # the router's validated plan
    }


if __name__ == "__main__":                      # only when run directly
    QUESTION = "How did customer OTIF change between FY2025 and FY2026?"  # a comparison question
    PLAN = [                                    # what the router would plan for it
        {"doc_type": "annual_review", "fiscal_year": "FY2025"},
        {"doc_type": "annual_review", "fiscal_year": "FY2026"},
    ]

    print(f"filter example:  {build_filter('annual_review', 'FY2026')}")  # show what OData looks like
    for key, results in search_plan(QUESTION, PLAN).items():  # one search per plan step
        print(f"\n{key}: {len(results)} candidates")            # how many came back
        for r in results[:5]:                                   # show the top five
            print(f"  hybrid {r['score']:.4f}  semantic {r['reranker_score'] or 0:.2f}  "
                  f"{r['text'][:70].replace(chr(10), ' ')}")    # chr(10) is a newline
