"""Daily product report: joins Shopify sales with GA4 product views for yesterday.

Writes reports/product_report_<date>.md. A missing source is reported, not fatal.
Output is a data-driven suggestion, not financial advice.
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from sources import SourceUnavailable
from sources.ga4 import fetch_product_views
from sources.shopify import fetch_product_sales
from sources.yahoo import fetch_price_trends

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "reports"
load_dotenv(BASE_DIR / ".env")


def yesterday_window() -> tuple[date, datetime, datetime]:
    today = datetime.now(timezone.utc).date()
    day = today - timedelta(days=1)
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return day, start, start + timedelta(days=1)


def classify(row: dict, median_conv: float) -> str:
    if row["views"] is None or row["units"] is None:
        return "Data incomplete: check the missing source"
    if row["units"] == 0 and row["views"] > 0:
        return "Views without sales: review price, listing, or stock"
    if row["units"] > 0 and row["conv"] is not None and row["conv"] >= median_conv:
        return "INVEST: strong conversion, consider more stock or ads"
    if row["units"] > 0:
        return "Sells but converts below median: test listing or pricing before adding spend"
    return "No activity"


def build_rows(sales: dict | None, views: dict | None) -> list[dict]:
    names = set(sales or {}) | set(views or {})
    rows = []
    for name in names:
        # A source that answered but has no row for this product means zero, not missing.
        s = (sales or {}).get(name, {"units": 0, "revenue": 0.0}) if sales is not None else None
        units = s["units"] if s is not None else None
        revenue = s["revenue"] if s is not None else None
        view_count = (views or {}).get(name, 0) if views is not None else None
        conv = (units / view_count) if (units is not None and view_count) else None
        rows.append({"name": name, "units": units, "revenue": revenue,
                     "views": view_count, "conv": conv})
    return rows


def main() -> int:
    day, start, end = yesterday_window()
    notes = []

    try:
        sales = fetch_product_sales(start, end)
    except SourceUnavailable as exc:
        sales = None
        notes.append(f"Shopify unavailable: {exc}")

    try:
        views = fetch_product_views(day)
    except SourceUnavailable as exc:
        views = None
        notes.append(f"GA4 unavailable: {exc}")

    market = []
    try:
        market = fetch_price_trends(30)
    except SourceUnavailable as exc:
        notes.append(f"Yahoo market data skipped: {exc}")

    rows = build_rows(sales, views)
    convs = sorted(r["conv"] for r in rows if r["conv"] is not None)
    median_conv = convs[len(convs) // 2] if convs else 0.0
    for r in rows:
        r["action"] = classify(r, median_conv)

    rows.sort(key=lambda r: ((r["revenue"] or 0), (r["views"] or 0)), reverse=True)

    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"product_report_{day.isoformat()}.md"
    lines = [f"# Product report: {day.isoformat()}", ""]
    if notes:
        lines += ["## Source status", *[f"- {n}" for n in notes], ""]
    lines += ["## Products (ranked by revenue, then views)", "",
              "| Product | Units | Revenue | Views | Conv. | Suggestion |",
              "|---|---|---|---|---|---|"]
    for r in rows:
        fmt = lambda x, f: "-" if x is None else f.format(x)
        lines.append(f"| {r['name']} | {fmt(r['units'], '{}')} | {fmt(r['revenue'], '{:.2f}')} | "
                     f"{fmt(r['views'], '{}')} | {fmt(r['conv'], '{:.1%}')} | {r['action']} |")
    if not rows:
        lines.append("| (no data) | | | | | |")
    if market:
        lines += ["", "## Market context (Yahoo Finance, 30-day price change)", "",
                  "| Ticker | Last | 30d change |", "|---|---|---|"]
        for m in market:
            if "error" in m:
                lines.append(f"| {m['ticker']} | - | {m['error']} |")
            else:
                lines.append(f"| {m['ticker']} | {m['last']:.2f} | {m['change_pct']:+.1f}% |")
    lines += ["", "_Data-driven suggestion only, not financial advice._", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    for n in notes:
        print("NOTE:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
