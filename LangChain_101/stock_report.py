"""Daily stock/ETF screen.

For each ticker in watchlist.txt it computes trend and risk from one year of prices.
Picks = tickers in an uptrend (above 50-day average, positive 3-month return), ranked by
return per unit of risk. Speculative tickers are shown but never picked.
Compares today's picks with the previous report: which picks were dropped and which are new.
Writes reports/stock_screen_<date>.md. Backward-looking analysis, NOT financial advice.
"""
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from sources import SourceUnavailable
from sources.yahoo import fetch_closes, load_watchlist

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "reports"
TOP_N = 3
PICKABLE_TIERS = {"core", "growth", "hedge"}
PICK_RE = re.compile(r"^\d+\. \*\*([A-Z.]+)\*\*")


def metrics(close: pd.Series) -> dict | None:
    close = close.dropna()
    if len(close) < 64:
        return None
    rets = close.pct_change().dropna()
    last = float(close.iloc[-1])
    ret_1m = last / float(close.iloc[-22]) - 1
    ret_3m = last / float(close.iloc[-64]) - 1
    vol_3m = float(rets.iloc[-63:].std() * np.sqrt(252))
    ma50 = float(close.iloc[-50:].mean())
    max_dd = float((close / close.cummax() - 1).min())
    return {
        "last": last, "ret_1m": ret_1m, "ret_3m": ret_3m, "vol_3m": vol_3m,
        "above_ma50": last > ma50, "max_dd_1y": max_dd,
        "score": ret_3m / vol_3m if vol_3m > 0 else 0.0,
    }


def pct(x: float) -> str:
    return f"{x:+.1%}"


def previous_picks(today: str) -> list[str]:
    """Picks from the most recent earlier stock_screen report."""
    earlier = sorted(p for p in REPORT_DIR.glob("stock_screen_*.md") if today not in p.name)
    if not earlier:
        return []
    picks = []
    for line in earlier[-1].read_text(encoding="utf-8").splitlines():
        m = PICK_RE.match(line)
        if m:
            picks.append(m.group(1))
    return picks


def main() -> int:
    today = date.today().isoformat()
    try:
        watch = load_watchlist()
        closes = fetch_closes(list(watch))
    except SourceUnavailable as exc:
        print(f"stock screen unavailable: {exc}")
        return 1

    rows = {}
    for t in watch:
        if t in closes.columns:
            m = metrics(closes[t])
            if m:
                m["tier"] = watch[t]
                rows[t] = m
    missing = [t for t in watch if t not in rows]

    eligible = sorted(
        (t for t, m in rows.items()
         if m["tier"] in PICKABLE_TIERS and m["above_ma50"] and m["ret_3m"] > 0),
        key=lambda t: rows[t]["score"], reverse=True,
    )
    picks = eligible[:TOP_N]
    before = previous_picks(today)
    dropped = [t for t in before if t not in picks]
    new = [t for t in picks if t not in before]

    lines = [f"# Stock screen: {today}", "",
             "_Backward-looking analysis of price trends, not financial advice. Past performance does not "
             "predict future results. Growth and speculative funds can lose a large share of their value. "
             "Only invest money you can afford to lose and check the risk with a licensed advisor._", ""]

    lines += ["## Changes since the last report", ""]
    if not before:
        lines += ["No earlier report to compare with yet.", ""]
    else:
        lines += [f"- **Drop:** {', '.join(dropped) if dropped else 'none'}",
                  f"- **New:** {', '.join(new) if new else 'none'}", ""]

    lines += ["## Today's picks (uptrend, best return per unit of risk)", ""]
    if picks:
        for i, t in enumerate(picks, 1):
            m = rows[t]
            lines.append(f"{i}. **{t}** ({m['tier']}): 3-month {pct(m['ret_3m'])}, "
                         f"volatility {m['vol_3m']:.1%}, 1-year max drop {m['max_dd_1y']:.1%}")
        lines.append("")
    else:
        lines += ["No ticker passed the screen today (none in an uptrend with a positive 3-month return). "
                  "Holding cash or waiting is a valid choice.", ""]

    lines += ["## All tickers", "",
              "| Ticker | Tier | Last | 1-month | 3-month | Volatility (3m) | Above 50-day avg | 1-yr max drop | Score |",
              "|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(rows, key=lambda t: rows[t]["score"], reverse=True):
        m = rows[t]
        lines.append(f"| {t} | {m['tier']} | {m['last']:.2f} | {pct(m['ret_1m'])} | {pct(m['ret_3m'])} | "
                     f"{m['vol_3m']:.1%} | {'yes' if m['above_ma50'] else 'no'} | "
                     f"{m['max_dd_1y']:.1%} | {m['score']:.2f} |")
    if missing:
        lines += ["", f"_No data for: {', '.join(missing)}_"]
    lines += ["", "**How to read it:** Score = 3-month return divided by annualized volatility (higher is better). "
              "'Above 50-day avg' means a short-term uptrend. Tiers: core = diversified base, growth = sector "
              "funds with higher swings, speculative = excluded from picks, hedge = a stabilizer. "
              "A 'Drop' means a pick no longer passes the screen: review your holdings in it.", ""]

    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"stock_screen_{today}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
