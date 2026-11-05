"""
==============================================================================
FILE        : portfolio_tools.py
PROJECT     : Portfolio X-Ray Crew (CrewAI + yfinance teaching project)
==============================================================================

PURPOSE
-------
Defines the TWO custom tools our agents use. Both pull live market data from
Yahoo Finance through the yfinance library:

    1. StockFundamentalsTool -> for each stock: company name, sector, price,
                                P/E ratio, market cap, and 1-year return.
                                Used by the Equity Research Analyst agent.

    2. PortfolioRiskTool     -> downloads 1 year of daily prices for all the
                                stocks plus the Nifty 50, then calculates:
                                volatility, worst drop, beta vs Nifty, which
                                stocks move together, and how many truly
                                separate "groups" the portfolio really has.
                                Used by the Portfolio Risk Analyst agent.

WHAT PROBLEM DOES IT SOLVE?
---------------------------
An investor with 5 stocks usually thinks "I own 5 different companies, so my
risk is spread out". But if 3 of them are banks, they rise and fall on the
same days. Then the portfolio behaves like 2 holdings, not 5.
An LLM cannot download prices and cannot reliably do statistics over 250
days of numbers. These tools do both in plain Python, so the numbers are
correct and repeatable. The LLM's job is to choose when to call the tools
and to explain the results.

KEY TERMS (explained simply)
----------------------------
    Daily return     : % change in price from one day to the next.
    Volatility       : how much the daily returns jump around, scaled to a year.
                       Higher = bigger ups and downs.
    Max drawdown     : the biggest fall from a peak to a later low in the year.
                       -20% means at the worst point you were down 20% from the top.
    Beta vs Nifty    : if Nifty moves 1%, how much does the portfolio move?
                       1.2 = it moves 1.2%. 0.8 = it moves 0.8%.
    Correlation      : a number from -1 to +1. Near +1 = two stocks go up and
                       down on the same days. Near 0 = no link.
    Hidden groups    : stocks whose correlation is above a threshold (default 0.5)
                       are put in the same group. Number of groups = number of
                       truly separate bets.

HOW TO RUN (quick self-test, no OpenAI key needed, needs internet)
------------------------------------------------------------------
    python portfolio_tools.py

EXPECTED OUTPUT
---------------
    A fundamentals table for 5 Indian stocks, then a risk report ending with
    a line like:  HIDDEN GROUPS : 5 stocks behave like 2 separate bets
==============================================================================
"""

# ---------------------------------------------------------------- IMPORTS ---
from typing import List, Type  # Type hints: List[...] = "a list of", Type[...] = "a class, not an object"

import numpy as np  # Fast maths on arrays; we use it for square roots and the weights calculation
import pandas as pd  # Tables of data (rows = days, columns = stocks); yfinance returns prices in this format
import yfinance as yf  # Free library that downloads stock data from Yahoo Finance
from crewai.tools import BaseTool  # The parent class every custom CrewAI tool inherits from
from pydantic import BaseModel, Field  # Pydantic describes and validates the inputs a tool expects

TRADING_DAYS = 252  # Number of days the stock market is open in a year; used to turn daily numbers into yearly ones


# =============================================================================
# TOOL 1 : STOCK FUNDAMENTALS
# =============================================================================
class StockFundamentalsInput(BaseModel):
    """Inputs for StockFundamentalsTool. The LLM must supply exactly this field."""

    tickers: List[str] = Field(  # One input: a list of ticker symbols
        ...,  # The three dots mean "required"
        description="Yahoo Finance ticker symbols. Indian NSE stocks end in .NS, e.g. ['TCS.NS', 'INFY.NS'].",  # The LLM reads this
    )


class StockFundamentalsTool(BaseTool):
    """Fetches basic company facts and the 1-year return for each ticker."""

    name: str = "Stock Fundamentals"  # Tool name shown to the LLM
    description: str = (  # Plain-English explanation the LLM reads to decide WHEN to use this tool
        "Fetches company name, sector, current price, P/E ratio, market cap and 1-year price return "
        "for a list of stock tickers from Yahoo Finance."
    )
    args_schema: Type[BaseModel] = StockFundamentalsInput  # CrewAI validates the LLM's arguments against this class

    def _run(self, tickers: List[str]) -> str:
        """The code that actually runs when the agent calls this tool."""
        lines = []  # One line of text per stock; joined at the end

        for symbol in tickers:  # Handle one stock at a time
            try:  # Network calls can fail; catch errors so one bad ticker does not crash the whole crew
                stock = yf.Ticker(symbol)  # Create a yfinance object for this ticker (no download yet)
                info = stock.info  # Download the company profile: a dictionary of facts like sector and P/E
                history = stock.history(period="1y")  # Download 1 year of daily prices as a table

                if history.empty:  # No price data usually means the ticker symbol is wrong
                    lines.append(f"{symbol}: ERROR - no price data found. Check the ticker symbol.")  # Tell the agent so it can fix it
                    continue  # Move on to the next ticker

                first_close = history["Close"].iloc[0]  # Closing price on the first day of the year (.iloc[0] = first row)
                last_close = history["Close"].iloc[-1]  # Closing price on the latest day (.iloc[-1] = last row)
                one_year_return = (last_close / first_close - 1) * 100  # % change over the year

                market_cap = info.get("marketCap")  # Total company value in rupees; .get returns None if the key is missing
                market_cap_cr = f"{market_cap / 1e7:,.0f} Cr" if market_cap else "n/a"  # 1 crore = 1,00,00,000 = 1e7; show "n/a" if missing
                pe = info.get("trailingPE")  # Price divided by last 12 months' earnings per share
                pe_text = f"{pe:.1f}" if pe else "n/a"  # Round to 1 decimal place, or "n/a" if missing

                lines.append(  # Build one readable line for this stock
                    f"{symbol} | {info.get('longName', 'n/a')} | Sector: {info.get('sector', 'n/a')} | "
                    f"Price: Rs. {last_close:,.2f} | P/E: {pe_text} | Market cap: Rs. {market_cap_cr} | "
                    f"1-year return: {one_year_return:+.1f}%"  # :+.1f always shows the sign, e.g. +12.3% or -4.0%
                )
            except Exception as error:  # Any problem (network down, Yahoo changed something)
                lines.append(f"{symbol}: ERROR - {error}")  # Report it as text instead of crashing

        return "\n".join(lines)  # Hand all lines back to the agent as one string


# =============================================================================
# TOOL 2 : PORTFOLIO RISK CALCULATOR
# =============================================================================
class PortfolioRiskInput(BaseModel):
    """Inputs for PortfolioRiskTool."""

    tickers: List[str] = Field(..., description="Ticker symbols in the portfolio, e.g. ['TCS.NS', 'INFY.NS'].")  # The stocks
    weights: List[float] = Field(  # How much of the money is in each stock
        ...,
        description="Share of money in each stock, in the SAME order as tickers, e.g. [0.6, 0.4]. Must add up to 1.",
    )
    benchmark: str = Field("^NSEI", description="Market index to compare against. Default ^NSEI (Nifty 50).")  # Has a default, so optional
    correlation_threshold: float = Field(  # Above this, two stocks are treated as "the same bet"
        0.5, description="Correlation above which two stocks are treated as moving together. Default 0.5."
    )


def find_groups(corr: pd.DataFrame, threshold: float) -> List[List[str]]:
    """Put stocks into groups: if A moves with B, and B moves with C, then A, B, C are one group."""
    groups = []  # Final list of groups; each group is a list of tickers
    unvisited = list(corr.columns)  # Stocks not yet placed in any group

    while unvisited:  # Keep going until every stock is in a group
        group = [unvisited.pop(0)]  # Start a new group with the first remaining stock (and remove it from unvisited)
        for member in group:  # Look at each stock in the group (the list grows as we add stocks)
            partners = [s for s in unvisited if corr.loc[member, s] > threshold]  # Remaining stocks that move with this one
            for partner in partners:  # Move each partner into the group
                group.append(partner)  # Adding to the list means the loop will also check this partner's partners
                unvisited.remove(partner)  # So it is not placed in another group
        groups.append(group)  # This group is complete

    return groups  # e.g. [['HDFCBANK.NS', 'ICICIBANK.NS', 'KOTAKBANK.NS'], ['TCS.NS', 'INFY.NS']]


def compute_risk_report(prices: pd.DataFrame, tickers: List[str], weights: List[float], benchmark: str, threshold: float) -> str:
    """All the maths, kept separate from the download so it can be tested with sample prices."""
    w = np.array(weights, dtype=float)  # Turn the weights list into a numpy array so we can multiply in one step
    w = w / w.sum()  # Rescale so the weights add up to exactly 1 (fixes inputs like [25, 20, 15, 20, 20])

    returns = prices.pct_change().dropna()  # Daily % change for every column; dropna removes the first day (it has no previous day)
    stock_returns = returns[tickers]  # Only the portfolio stocks, not the benchmark
    portfolio_returns = stock_returns @ w  # "@" = weighted sum of each day's returns -> the portfolio's daily return
    bench_returns = returns[benchmark]  # The Nifty's daily returns

    report = [f"PERIOD : {returns.index[0].date()} to {returns.index[-1].date()} ({len(returns)} trading days)"]  # Date range used

    # ---- Volatility ---------------------------------------------------
    port_vol = portfolio_returns.std() * np.sqrt(TRADING_DAYS) * 100  # Daily spread x sqrt(252) = yearly spread, in %
    bench_vol = bench_returns.std() * np.sqrt(TRADING_DAYS) * 100  # Same for Nifty, for comparison
    report.append(f"VOLATILITY (yearly) : portfolio {port_vol:.1f}% vs Nifty {bench_vol:.1f}%")

    # ---- Max drawdown -------------------------------------------------
    growth = (1 + portfolio_returns).cumprod()  # Value of Rs. 1 invested on day 1, day by day
    drawdown = growth / growth.cummax() - 1  # How far below its highest point so far the portfolio is each day
    report.append(f"MAX DRAWDOWN : {drawdown.min() * 100:.1f}% (worst fall from a peak, reached on {drawdown.idxmin().date()})")

    # ---- Total return ---------------------------------------------------
    report.append(f"1-YEAR RETURN : portfolio {(growth.iloc[-1] - 1) * 100:+.1f}% vs Nifty {((1 + bench_returns).prod() - 1) * 100:+.1f}%")

    # ---- Beta -----------------------------------------------------------
    beta = portfolio_returns.cov(bench_returns) / bench_returns.var()  # How much the portfolio moves for each 1% Nifty move
    report.append(f"BETA vs Nifty : {beta:.2f} (Nifty moves 1% -> portfolio moves about {beta:.2f}%)")

    # ---- Correlation pairs ---------------------------------------------
    corr = stock_returns.corr()  # Table of correlation between every pair of stocks
    report.append(f"PAIRS MOVING TOGETHER (correlation > {threshold}):")
    found_pair = False  # Becomes True if we find at least one pair
    for i, a in enumerate(tickers):  # Each stock...
        for b in tickers[i + 1:]:  # ...paired only with the stocks after it, so each pair appears once
            if corr.loc[a, b] > threshold:  # This pair moves together
                report.append(f"  - {a} & {b}: {corr.loc[a, b]:.2f}")
                found_pair = True
    if not found_pair:  # No pair crossed the threshold
        report.append("  - none")

    # ---- Hidden groups ---------------------------------------------------
    groups = find_groups(corr, threshold)  # Cluster the stocks into truly separate bets
    report.append("GROUPS (stocks in one group rise and fall together):")  # Header so the group lines are not read as pairs
    for n, group in enumerate(groups, start=1):  # Print each group with its total weight
        group_weight = sum(w[tickers.index(t)] for t in group) * 100  # Add up the weights of the stocks in this group
        report.append(f"  Group {n} ({group_weight:.0f}% of money): {', '.join(group)}")
    report.append(f"HIDDEN GROUPS : {len(tickers)} stocks behave like {len(groups)} separate bets")  # The headline finding

    return "\n".join(report)  # Hand the whole report back as one string


class PortfolioRiskTool(BaseTool):
    """Downloads 1 year of prices and runs compute_risk_report on them."""

    name: str = "Portfolio Risk Calculator"  # Tool name shown to the LLM
    description: str = (  # Tells the LLM what this tool does
        "Downloads 1 year of daily prices for a portfolio and a benchmark index, then calculates "
        "volatility, max drawdown, 1-year return, beta, which stocks move together, and how many "
        "truly separate groups the portfolio has."
    )
    args_schema: Type[BaseModel] = PortfolioRiskInput  # CrewAI validates the LLM's arguments against this class

    def _run(self, tickers: List[str], weights: List[float], benchmark: str = "^NSEI", correlation_threshold: float = 0.5) -> str:
        if len(tickers) != len(weights):  # Every stock needs exactly one weight
            return f"ERROR: {len(tickers)} tickers but {len(weights)} weights. Give one weight per ticker."  # Agent reads this and retries
        try:
            data = yf.download(tickers + [benchmark], period="1y", auto_adjust=True, progress=False)  # Download all prices in one call; auto_adjust corrects for splits and dividends
            prices = data["Close"].dropna()  # Keep only closing prices, and only days where every stock has a price
            missing = [t for t in tickers + [benchmark] if t not in prices.columns or prices[t].isna().all()]  # Tickers that came back empty
            if missing:  # At least one ticker failed
                return f"ERROR: no price data for {missing}. Check the ticker symbols."
            return compute_risk_report(prices, tickers, weights, benchmark, correlation_threshold)  # Do the maths
        except Exception as error:  # Network or Yahoo problem
            return f"ERROR: could not download prices - {error}"


# =============================================================================
# SELF-TEST: run "python portfolio_tools.py" (needs internet, no OpenAI key)
# =============================================================================
if __name__ == "__main__":  # Only runs when this file is executed directly, not when crew.py imports it
    sample = ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "TCS.NS", "INFY.NS"]  # The same portfolio crew.py uses
    print("=== TOOL 1: Stock Fundamentals ===")
    print(StockFundamentalsTool().run(tickers=sample))  # .run() is how CrewAI calls a tool
    print("\n=== TOOL 2: Portfolio Risk Calculator ===")
    print(PortfolioRiskTool().run(tickers=sample, weights=[0.25, 0.20, 0.15, 0.20, 0.20]))