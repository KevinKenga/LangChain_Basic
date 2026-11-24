"""
Offline tests for plan-driven search: one filtered search per plan step, and
every filter pinned to both doc_type and fiscal_year.

No Azure call is made: the search client and the embedding call are faked.
"""

from types import SimpleNamespace               # a quick object with attributes

from retrieval import search as search_module   # the search under test

PLAN = [
    {"doc_type": "annual_review", "fiscal_year": "FY2025"},
    {"doc_type": "annual_review", "fiscal_year": "FY2026"},
    {"doc_type": "procurement_policy", "fiscal_year": "FY2026"},
]


def fake_clients(monkeypatch, filters):
    """Replace Azure AI Search and Azure OpenAI with recorders."""
    class FakeSearch:
        def search(self, **kwargs):
            filters.append(kwargs["filter"])    # remember the OData filter of each call
            return []                           # no hits needed for this test

    fake_embeddings = SimpleNamespace(create=lambda **kw: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])]))
    monkeypatch.setattr(search_module, "search_client", lambda: FakeSearch())
    monkeypatch.setattr(search_module, "openai_client", lambda: SimpleNamespace(embeddings=fake_embeddings))


def test_one_search_per_plan_step_keyed_by_the_step(monkeypatch):
    filters = []
    fake_clients(monkeypatch, filters)
    results = search_module.search_plan("How did OTIF change?", PLAN)

    assert list(results) == ["annual_review · FY2025", "annual_review · FY2026",
                             "procurement_policy · FY2026"]  # one key per search, in plan order
    assert len(filters) == len(PLAN)                        # exactly one call per step


def test_every_filter_names_both_doc_type_and_year(monkeypatch):
    filters = []
    fake_clients(monkeypatch, filters)
    search_module.search_plan("q", PLAN)

    for step, odata in zip(PLAN, filters):
        assert f"doc_type eq '{step['doc_type']}'" in odata        # the document is pinned
        assert f"fiscal_year eq '{step['fiscal_year']}'" in odata  # and so is the year


def test_the_fy2026_search_cannot_see_fy2025(monkeypatch):
    filters = []
    fake_clients(monkeypatch, filters)
    search_module.search_plan("What was the average import lead time in FY2026?", PLAN)  # Q4

    fy2026 = filters[1]                         # the annual_review · FY2026 search
    assert "FY2026" in fy2026 and "FY2025" not in fy2026  # no cross-year leakage
