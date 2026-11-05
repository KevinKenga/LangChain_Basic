"""
Task Definitions Module.

This module defines the specific work orders (Tasks) that the agents must execute.
It acts as the 'Prompt Engineering' layer of the application.

Key Features:
    - Context Injection: The Strategist's task explicitly waits for and receives 
      the output from the Quant's task to ensure data-driven reasoning.
    - Output Formatting: Enforces Markdown structure for the final report.
"""

from crewai import Task
from crewai import Agent

def create_tasks(quant_agent: Agent, strategist_agent: Agent, ticker: str) -> list[Task]:
    """
    Creates the sequence of tasks for the financial analysis workflow.

    Args:
        quant_agent (Agent): The agent responsible for financial metrics.
        strategist_agent (Agent): The agent responsible for news and synthesis.
        ticker (str): The stock ticker symbol to analyze (e.g., 'NVDA').

    Returns:
        list[Task]: A list of Task objects in the order of execution.
    """
    
    # ==========================================================================
    # Task 1: Quantitative Data Collection (The Foundation)
    # ==========================================================================
    quant_task = Task(
        description=(
            f"Analyze the financial health of ticker '{ticker}'. "
            "1. Use the FundamentalAnalysisTool to fetch P/E, EPS, Beta, and Market Cap. "
            "2. Use the CompareStocksTool to compare '{ticker}' against 'SPY' (S&P 500) "
            "   to see its relative performance over the last year. "
            "3. Identify any major numerical red flags (e.g., negative EPS, extremely high P/E). "
            "Output a concise summary of the hard numbers."
        ),
        expected_output="A structured summary of financial metrics and 1-year performance comparison.",
        agent=quant_agent
    )

    # ==========================================================================
    # Task 2: Strategic Synthesis (The Recommendation)
    # ==========================================================================
    recommendation_task = Task(
        description=(
            f"Formulate a final investment recommendation for '{ticker}'. "
            "1. Read the financial metrics provided by the Quantitative Analyst. "
            "2. Use the SentimentSearchTool to find the top 3 recent news articles "
            "   or analyst ratings for '{ticker}'. Look for leadership changes, "
            "   regulatory lawsuits, or product launches. "
            "3. SYNTHESIZE the numbers (Quant) with the narrative (News). "
            "   - If numbers are good but news is bad (e.g., lawsuit), be cautious. "
            "   - If numbers are bad but news is hype, be skeptical. "
            "4. Provide a final verdict: 'BUY', 'SELL', or 'HOLD', with a clear reasoning."
        ),
        expected_output="A comprehensive Markdown report including the verdict, key metrics, and news highlights.",
        agent=strategist_agent,
        context=[quant_task],  # <--- CRITICAL: This passes Task 1's output to this agent
        output_file=f"investment_report_{ticker}.md" # Saves the final report to disk
    )

    return [quant_task, recommendation_task]