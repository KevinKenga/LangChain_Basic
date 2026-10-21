'''
web_report_agent.py
Autonomous research agent: it searches the web for a topic,
reads the most relevant pages and writes a markdown report.

Run:
    python web_report_agent.py "topic to research"
'''

import html
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import requests
from ddgs import DDGS
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv(override=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")


def _is_recent(date_str: str, hours: int) -> bool:
    """True if an article's ISO date is within the last `hours`. Unknown dates are dropped."""
    try:
        published = datetime.fromisoformat(date_str)
    except (TypeError, ValueError):
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published >= datetime.now(timezone.utc) - timedelta(hours=hours)


@tool
def web_search(query: str, hours: int = 24) -> str:
    """Search recent news (default: last 24 hours) and return title, url, date and snippet.
    Use a larger `hours` value (e.g. 168 for a week) only if the last 24 hours has nothing."""
    try:
        # timelimit='d' is applied by the search engine, but it is not reliable,
        # so results are also filtered by their published date below.
        results = DDGS().news(query, timelimit="d", max_results=15)
    except Exception as exc:  # ddgs raises when a query has no hits or is rate-limited
        return f"Search failed for '{query}': {exc}. Try different wording."
    recent = [r for r in results if _is_recent(r.get("date", ""), hours)]
    if not recent:
        return f"No articles from the last {hours} hours for '{query}'. Try different wording."
    lines = []
    for r in recent[:6]:
        lines.append(
            f"- {r.get('title', '')} ({r.get('date', '')}, {r.get('source', '')})\n"
            f"  URL: {r.get('url', '')}\n  Snippet: {r.get('body', '')}"
        )
    return "\n".join(lines)


@tool
def fetch_page(url: str) -> str:
    """Fetch a web page by URL and return its readable text (first 4000 characters)."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as exc:  # blocked (403), timeout, etc. - let the agent try another source
        return f"Could not fetch {url}: {exc}. Use another source."
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", resp.text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text))
    return text[:4000]


agent = create_agent(
    model=ChatOpenAI(model="gpt-4o-mini", temperature=0),
    tools=[web_search, fetch_page],
    system_prompt=(
        "You are an autonomous research agent. "
        "Use the web_search tool to find news about the user's topic from the last 24 hours, "
        "and fetch_page when a snippet looks important but needs more detail. "
        "Only report items that web_search returned with a date from the last 24 hours; "
        "do not use older articles, even if they look relevant. "
        "If there is nothing recent, say so in the report instead of filling it with old news. "
        "Do at least two searches with different phrasing before concluding. "
        "Then write a concise markdown report with: "
        "a title, a 3-sentence summary, 3-5 key findings as bullet points, "
        "and a Sources section listing the URLs you actually used."
    ),
)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def run(topic: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": topic}]})
    return result["messages"][-1].content


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python web_report_agent.py \"topic to research\"")
        sys.exit(1)

    topic = " ".join(sys.argv[1:])
    print(f"Researching: {topic}\n")
    report = run(topic)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{slugify(topic)}_{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\nReport saved to: {path}")
