"""
Financial Data Extraction Module.

This module provides CrewAI tools for fetching structured financial data 
from the Yahoo Finance API. It is designed to be the "Quantitative Analyst" 
component of the system, handling hard numbers and performance metrics.

Classes:
    FundamentalAnalysisTool: Fetches snapshot metrics (P/E, Beta, Cap).
    CompareStocksTool: Calculates relative performance over time.

Dependencies:
    - yfinance: For accessing market data.
    - crewai_tools: For integration with the agent framework.
"""

from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import yfinance as yf

# ==============================================================================
# Input Schemas (Pydantic Models)
# ==============================================================================

class StockAnalysisInput(BaseModel):
    """
    Input schema for the FundamentalAnalysisTool.
    Enforces that a ticker symbol is provided as a string.
    """
    ticker: str = Field(
        ..., 
        description="The stock ticker symbol (e.g., 'AAPL', 'NVDA', 'MSFT')."
    )

class CompareStocksInput(BaseModel):
    """
    Input schema for the CompareStocksTool.
    Requires two distinct tickers for side-by-side comparison.
    """
    ticker_a: str = Field(..., description="The first stock ticker to analyze.")
    ticker_b: str = Field(..., description="The second stock ticker to compare against.")


# ==============================================================================
# Tool Definitions
# ==============================================================================

class FundamentalAnalysisTool(BaseTool):
    """
    A CrewAI tool that extracts key fundamental financial metrics for a stock.
    
    This tool acts as a 'Screening Analyst', providing the raw data needed
    to determine if a stock is overvalued, undervalued, or volatile.
    """
    
    name: str = "Fetch Fundamental Metrics"
    description: str = (
        "Fetches key financial metrics for a specific stock ticker. "
        "Useful for quantitative analysis. Returns JSON-formatted data including "
        "P/E Ratio, Beta, Market Cap, EPS, and 52-week High/Low."
    )
    args_schema: Type[BaseModel] = StockAnalysisInput

    def _run(self, ticker: str) -> str:
        """
        Executes the data fetch from Yahoo Finance.

        Args:
            ticker (str): The stock symbol to look up.

        Returns:
            str: A stringified JSON dictionary containing selected metrics, 
                 or an error message string if the fetch fails.
        """
        try:
            # Initialize the Ticker object
            stock = yf.Ticker(ticker)
            info: Dict[str, Any] = stock.info
            
            # We explicitly select only robust metrics to avoid context-window bloat.
            # Sending ALL yfinance data (100+ keys) often confuses the LLM.
            metrics = {
                "Ticker": ticker.upper(),
                "Current Price": info.get("currentPrice", "N/A"),
                "Market Cap": info.get("marketCap", "N/A"),
                "P/E Ratio (Trailing)": info.get("trailingPE", "N/A"),
                "Forward P/E": info.get("forwardPE", "N/A"),
                "PEG Ratio": info.get("pegRatio", "N/A"),
                "Beta (Volatility)": info.get("beta", "N/A"),
                "EPS (Trailing)": info.get("trailingEps", "N/A"),
                "52 Week High": info.get("fiftyTwoWeekHigh", "N/A"),
                "52 Week Low": info.get("fiftyTwoWeekLow", "N/A"),
                "Analyst Recommendation": info.get("recommendationKey", "none")
            }
            return str(metrics)

        except Exception as e:
            # Graceful error handling allows the Agent to self-correct 
            # (e.g., by retrying with a corrected ticker symbol)
            return f"Error fetching fundamental data for '{ticker}': {str(e)}"


class CompareStocksTool(BaseTool):
    """
    A CrewAI tool that calculates relative performance between two assets.
    
    This tool is used to answer questions like 'Did Nvidia beat Apple last year?'
    by calculating the percentage change in price over a 1-year period.
    """
    
    name: str = "Compare Stock Performance"
    description: str = (
        "Compares the historical performance of two stocks over the last 365 days. "
        "Returns the percentage gain or loss for both assets."
    )
    args_schema: Type[BaseModel] = CompareStocksInput

    def _run(self, ticker_a: str, ticker_b: str) -> str:
        """
        Fetches historical data and calculates percentage return.

        Formula: ((Last Price - First Price) / First Price) * 100

        Args:
            ticker_a (str): First stock symbol.
            ticker_b (str): Second stock symbol.

        Returns:
            str: A formatted summary of the 1-year performance comparison.
        """
        try:
            # Download only the 'Close' column for the last 1 year
            tickers = f"{ticker_a} {ticker_b}"
            data = yf.download(tickers, period="1y", progress=False)['Close']
            
            # Helper function to calculate return
            def calculate_return(symbol: str) -> float:
                start_price = data[symbol].iloc[0]
                end_price = data[symbol].iloc[-1]
                return ((end_price - start_price) / start_price) * 100

            perf_a = calculate_return(ticker_a)
            perf_b = calculate_return(ticker_b)

            return (
                f"Performance Comparison (Last 1 Year):\n"
                f"- {ticker_a.upper()}: {perf_a:.2f}%\n"
                f"- {ticker_b.upper()}: {perf_b:.2f}%"
            )

        except Exception as e:
            return f"Error comparing stocks '{ticker_a}' and '{ticker_b}': {str(e)}"