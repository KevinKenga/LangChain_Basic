"""Yahoo Finance (yfinance): daily closing prices for a watchlist of tickers.

Reads watchlist.txt in the LangChain_101 folder. Each line: TICKER [tier] [description].
'#' starts a comment. Raises SourceUnavailable if no tickers are configured or the download fails.
"""
import os

import pandas as pd

from sources import SourceUnavailable

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(BASE_DIR, "watchlist.txt")


def load_watchlist() -> dict[str, str]:
    """Return {ticker: risk_tier}, in file order."""
    if not os.path.exists(WATCHLIST):
        raise SourceUnavailable(f"watchlist not found: {WATCHLIST}")
    out = {}
    with open(WATCHLIST, encoding="utf-8") as f:
        for line in f:
            body = line.split("#", 1)[0].strip()
            if not body:
                continue
            parts = body.split()
            tier = parts[1] if len(parts) > 1 else "unlabeled"
            out[parts[0]] = tier
    if not out:
        raise SourceUnavailable("watchlist.txt has no tickers")
    return out


def fetch_closes(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """Return a DataFrame: index = date, columns = ticker, values = adjusted close."""
    try:
        import yfinance as yf

        hist = yf.download(tickers, period=period, interval="1d",
                           auto_adjust=True, progress=False, group_by="ticker")
    except Exception as exc:
        raise SourceUnavailable(f"yfinance download failed: {exc}") from exc
    if hist is None or hist.empty:
        raise SourceUnavailable("yfinance returned no data")

    closes = {}
    for t in tickers:
        if t in hist.columns.get_level_values(0):
            closes[t] = hist[t]["Close"]
    return pd.DataFrame(closes).sort_index()
