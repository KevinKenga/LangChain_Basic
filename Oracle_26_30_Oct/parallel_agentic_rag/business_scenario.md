# Business Scenario: "Should We Build It?" — Parallel Agentic RAG for Product Decisions

## 1. The Company

**NimbusDesk** is a SaaS company in Bengaluru. It sells a helpdesk / ticketing product to small and mid-sized businesses (about 1,200 paying accounts).

The product team is preparing the **Q1 2027 roadmap**. For every feature request they must answer:

> "Should we build this feature next quarter, and why?"

## 2. The Problem

To answer that one question, a product manager (PM) has to read **three** separate product-management documents, each owned by a different team:

| # | Document (PDF) | Owned by | What it contains |
|---|----------------|----------|------------------|
| 1 | `customer_feedback_report.pdf` | Customer Success | Survey results, NPS, feature requests with counts, churn interviews, customer concerns |
| 2 | `product_usage_analytics.pdf` | Data / Analytics | Accounts by segment, churn %, feature adoption, response times, SLA breaches, pilot results |
| 3 | `competitor_analysis.pdf` | Product Marketing | What 3 competitors offer, their pricing, win/loss data, market threats |

Today the PM reads these one by one. This causes three issues:

1. **It is slow.** Reading all three reports takes hours for each feature.
2. **Information gets missed.** A complaint in the feedback report is often explained by a number in the analytics report, but nobody connects them.
3. **The answer is not traceable.** Leadership asks "which page did this number come from?" and the PM cannot say.

## 3. Example Questions the System Must Answer

- "Should we build **AI-suggested ticket replies** in Q1?"
- "Customers keep asking for a **WhatsApp integration** — is it worth it?"
- "Why is **churn rising in the 11–50 seat segment**, and what should we fix first?"
- "Should we prioritise **WhatsApp or AI replies** first?"

## 4. What We Will Build

An **Agentic RAG system built with LangGraph** where **four agent nodes run in parallel**. Each node does a **different task**.

| Node | Task | Searches |
|------|------|----------|
| **Customer Voice Agent** | What are customers asking for and complaining about? | `customer_feedback_report.pdf` only |
| **Usage Analytics Agent** | What do the numbers (churn, adoption, response time) say? | `product_usage_analytics.pdf` only |
| **Market Agent** | What are competitors doing, and are we losing deals? | `competitor_analysis.pdf` only |
| **Risk Agent** | What risks, concerns or costs could make this a bad idea? | **All 3 PDFs** |

### Flow of one question

1. The user types a question in an HTML page.
2. The HTML page sends the question to a **FastAPI** server (`POST /ask`).
3. FastAPI starts the LangGraph graph.
4. The graph **fans out**: the same question goes to all 4 agent nodes **at the same time**.
5. Inside each agent node, three steps run in order:
   - **Retrieve**: pick the top 10 chunks by embedding similarity (fast, rough).
   - **Re-rank**: a cross-encoder model reads the question and each of those 10 chunks together, scores each again, and keeps the top 3.
   - **Answer**: the LLM writes a short finding using only those 3 chunks, citing page numbers.
6. The graph **fans in**: a **Synthesizer node** waits for all 4 findings, then writes one recommendation (**Build now / Build later / Don't build**) with reasons and citations.
7. FastAPI returns the result and all timings to the HTML page.

## 5. What the UI Must Show (Teaching Goals)

### Goal A: parallelism is visible
For each of the 4 agent nodes plus the synthesizer:
- start and end time (ms from when the request began)
- duration in ms, split into **retrieve / re-rank / LLM**
- a timeline bar, so students see the 4 agent bars **overlap**

Two totals:
- **Actual wall-clock time** (parallel run)
- **Sum of the 4 agent durations** (what a one-after-another run would cost)

### Goal B: re-ranking is visible
For each agent, a **before vs after re-ranking table**:

| Chunk | Page | Rank by vector search | Vector score | Rank after re-ranking | Re-rank score | Kept? |

The PDFs deliberately contain "keyword trap" chunks (e.g. a paragraph that says "WhatsApp" but is about the support team's internal shift chat). Vector search ranks these high; the re-ranker pushes them down.

## 6. Success Criteria

1. Each question in Section 3 returns a recommendation citing at least 2 PDFs with page numbers.
2. The timeline shows all 4 agent nodes starting within a few ms of each other.
3. Wall-clock time is clearly lower than the sum of the 4 agent durations.
4. At least one question shows a chunk changing rank after re-ranking, and a keyword-trap chunk dropped.
5. Every line of code has a comment explaining what it does and why.

## 7. Out of Scope

- No login, no database (vectors are kept in memory, built at server start)
- No token streaming
- No cloud deployment; runs on a laptop
