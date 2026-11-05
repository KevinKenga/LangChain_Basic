"""
Agent Definitions Module.

This module defines the specific AI personas (Agents) that will execute the 
financial analysis workflow. Each agent is equipped with a distinct set of tools 
and a specific backstory to ensure separation of concerns.

Agents:
    1. Quantitative Analyst: Focuses on hard financial metrics (P/E, Beta, etc.).
    2. Investment Strategist: Focuses on qualitative news, sentiment, and synthesis.
"""

from typing import Tuple
from crewai import Agent
from src.agents.tools.financial import FundamentalAnalysisTool, CompareStocksTool
from src.agents.tools.scraper import SentimentSearchTool

def create_agents() -> Tuple[Agent, Agent]:
    """
    Factory function to instantiate the agents for the financial crew.

    Returns:
        Tuple[Agent, Agent]: A tuple containing (quant_agent, strategist_agent).
    """

    # ==========================================================================
    # 1. The Quantitative Analyst (The "Math Brain")
    # ==========================================================================
    # This agent deals ONLY with hard numbers. It uses yfinance tools.
    # It does not hallucinate feelings; it looks at spreadsheets.
    quant_agent = Agent(
        role='Senior Quantitative Analyst',
        goal='Analyze the financial health and historical performance of the target stock.',
        backstory=(
            "You are a veteran financial analyst with 20 years of experience on Wall Street. "
            "You do not care about rumors or news headlines. You only trust hard data. "
            "You judge companies strictly by their balance sheets, P/E ratios, "
            "earnings growth (EPS), and volatility (Beta). "
            "Your reports are concise, number-heavy, and brutally honest."
        ),
        verbose=True,
        memory=True,
        tools=[
            FundamentalAnalysisTool(),
            CompareStocksTool()
        ],
        allow_delegation=False  # We want them to do their own work, not ask others.
    )

    # ==========================================================================
    # 2. The Investment Strategist (The "Big Picture Brain")
    # ==========================================================================
    # This agent deals with NEWS and SENTIMENT. It uses Firecrawl.
    # Its job is to explain "Why" the numbers are the way they are.
    strategist_agent = Agent(
        role='Chief Investment Strategist',
        goal='Synthesize quantitative data with market sentiment to form a recommendation.',
        backstory=(
            "You are a visionary investment strategist who looks beyond the spreadsheet. "
            "You understand that stock prices are driven by human psychology, news, "
            "and leadership changes. You read the news to find the 'narrative' "
            "behind the stock. You combine the Quant's numbers with your news findings "
            "to give a final 'Buy', 'Sell', or 'Hold' recommendation."
        ),
        verbose=True,
        memory=True,
        tools=[
            SentimentSearchTool()
        ],
        allow_delegation=False
    )

    return quant_agent, strategist_agent