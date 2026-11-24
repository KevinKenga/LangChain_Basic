"""
Offline tests for the router: the free keyword fallback, and the Python
validation that cleans up whatever the model wrote.

No Azure call is made anywhere in this file.
"""

import pytest                                   # the test runner

import config                                   # valid pairs, search cap
from azure_clients import openai_client         # cleared, so "no key" really means no client
from graph import router                        # the router under test
from graph.router import (                      # the pieces under test
    COMPARE_YEARS,
    CROSS_DOCUMENT,
    FALLBACK,
    LOOKUP,
    RouterPlan,
    keyword_plan,
    plan_question,
    validate_plan,
)


def pairs(plan) -> list:
    """The plan's searches as (doc_type, fiscal_year) tuples, for easy comparison."""
    return [(step["doc_type"], step["fiscal_year"]) for step in plan.searches]


# ------------------------------------------------------------------------------
# The fallback, with the OpenAI key removed
# ------------------------------------------------------------------------------

@pytest.fixture
def no_openai_key(monkeypatch):
    """Make every Azure OpenAI call fail, exactly as it would with no key in .env."""
    monkeypatch.setattr(config, "AZURE_OPENAI_API_KEY", None)
    openai_client.cache_clear()                 # drop any client built by an earlier test
    yield
    openai_client.cache_clear()                 # and leave no broken client behind


def test_fallback_plans_both_reviews_for_a_year_comparison(no_openai_key):
    plan = plan_question("How did customer OTIF change between FY2025 and FY2026?")  # Q1
    assert plan.source == FALLBACK              # the model call failed, so the free router answered
    assert plan.intent == COMPARE_YEARS
    assert pairs(plan) == [("annual_review", "FY2025"), ("annual_review", "FY2026")]


def test_fallback_plans_the_policy_for_an_approval_lookup(no_openai_key):
    plan = plan_question("Who must approve a purchase order of 15 crore?")  # Q7
    assert plan.source == FALLBACK
    assert plan.intent == LOOKUP
    assert pairs(plan) == [("procurement_policy", "FY2026")]


def test_fallback_plans_two_documents_for_a_rule_check(no_openai_key):
    plan = plan_question("Which single-sourced suppliers breach the dual-sourcing rule in the procurement policy?")  # Q9
    assert plan.source == FALLBACK
    assert plan.intent == CROSS_DOCUMENT
    assert set(pairs(plan)) == {("risk_register", "FY2026"), ("procurement_policy", "FY2026")}


def test_fallback_never_plans_more_than_the_cap():
    plan = keyword_plan("supplier policy warehouse OTIF risk score freight")  # words from every document
    assert len(plan.searches) <= config.MAX_SEARCHES
    assert all((s["doc_type"], s["fiscal_year"]) in config.VALID_PAIRS for s in plan.searches)


def test_fallback_always_returns_a_valid_plan():
    plan = keyword_plan("How are we doing on the chip problem?")  # Q11: no keyword at all
    assert plan.searches and plan.intent in (LOOKUP, CROSS_DOCUMENT)
    assert all((s["doc_type"], s["fiscal_year"]) in config.VALID_PAIRS for s in plan.searches)


# ------------------------------------------------------------------------------
# Validation in plain Python
# ------------------------------------------------------------------------------

def test_validation_drops_pairs_that_do_not_exist():
    plan = validate_plan(LOOKUP, [{"doc_type": "annual_review", "fiscal_year": "FY2024"},
                                  {"doc_type": "payroll", "fiscal_year": "FY2026"},
                                  {"doc_type": "risk_register", "fiscal_year": "FY2026"}], "r")
    assert pairs(plan) == [("risk_register", "FY2026")]  # only the real pair survived


def test_validation_removes_repeats():
    plan = validate_plan(LOOKUP, [{"doc_type": "risk_register", "fiscal_year": "FY2026"},
                                  {"doc_type": "risk_register", "fiscal_year": "FY2026"}], "r")
    assert pairs(plan) == [("risk_register", "FY2026")]


def test_validation_caps_at_three_searches():
    plan = validate_plan(CROSS_DOCUMENT, [{"doc_type": "annual_review", "fiscal_year": "FY2025"},
                                          {"doc_type": "annual_review", "fiscal_year": "FY2026"},
                                          {"doc_type": "risk_register", "fiscal_year": "FY2026"},
                                          {"doc_type": "logistics_report", "fiscal_year": "FY2026"},
                                          {"doc_type": "procurement_policy", "fiscal_year": "FY2026"}], "r")
    assert len(plan.searches) == config.MAX_SEARCHES


def test_validation_forces_both_reviews_for_a_comparison():
    plan = validate_plan(COMPARE_YEARS, [{"doc_type": "annual_review", "fiscal_year": "FY2026"}], "r")
    assert pairs(plan) == [("annual_review", "FY2025"), ("annual_review", "FY2026")]


def test_validation_rejects_an_unknown_intent():
    assert validate_plan("summarise", [{"doc_type": "risk_register", "fiscal_year": "FY2026"}], "r") is None


def test_validation_rejects_a_plan_with_nothing_left():
    assert validate_plan(LOOKUP, [{"doc_type": "payroll", "fiscal_year": "FY2026"}], "r") is None


# ------------------------------------------------------------------------------
# The model's plan is used when it is usable
# ------------------------------------------------------------------------------

def test_usable_model_plan_is_used(monkeypatch):
    monkeypatch.setattr(router, "model_plan", lambda q: RouterPlan(
        intent=LOOKUP, searches=[{"doc_type": "logistics_report", "fiscal_year": "FY2026"}], reason="stub"))
    plan = plan_question("Which warehouse had the highest utilisation?")
    assert plan.intent == LOOKUP and pairs(plan) == [("logistics_report", "FY2026")]


def test_unusable_model_plan_falls_back(monkeypatch):
    monkeypatch.setattr(router, "model_plan", lambda q: None)  # the model's plan did not validate
    plan = plan_question("Who must approve a purchase order of 15 crore?")
    assert plan.source == FALLBACK and plan.intent == LOOKUP
