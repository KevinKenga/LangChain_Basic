'''
daily_report_agent.py
Promptless daily runner: researches every topic in topics.txt with the
web agent, saves one report per topic, and a combined daily digest.
Run it from cron/launchd, or manually. No user input needed.

    python daily_report_agent.py              # topics from topics.txt
    python daily_report_agent.py "topic"      # ad-hoc topics instead
'''

import os
import sys
from datetime import date, datetime

from stock_report import main as stock_main
from web_report_agent import REPORTS_DIR, run, slugify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(BASE_DIR, "topics.txt")


def load_topics() -> list:
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return ["latest developments in generative AI",
            "notable machine learning research breakthroughs this week"]


def main() -> None:
    topics = sys.argv[1:] or load_topics()
    today = date.today().isoformat()
    sections = []

    for topic in topics:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] researching: {topic}")
        try:
            report = run(topic)
        except Exception as exc:
            report = f"# {topic}\n\nReport failed: {exc}"
            print(f"  ERROR: {exc}")
        path = os.path.join(REPORTS_DIR, f"{slugify(topic)}_{today}.md")
        os.makedirs(REPORTS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  saved: {path}")
        sections.append(report)

    digest_path = os.path.join(REPORTS_DIR, f"daily_digest_{today}.md")
    digest = f"# Daily AI Report - {today}\n\n" + "\n\n---\n\n".join(sections)
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(digest)
    print(f"\nDigest saved to: {digest_path}")

    try:
        stock_main()
    except Exception as exc:  # the news digest is already saved; keep the job alive
        print(f"stock screen failed: {exc}")


if __name__ == "__main__":
    main()
