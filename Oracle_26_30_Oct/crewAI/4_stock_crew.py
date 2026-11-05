"""
==============================================================================
FILE        : crew.py
PROJECT     : Portfolio X-Ray Crew (CrewAI + yfinance teaching project)
==============================================================================

PURPOSE
-------
Builds and runs a crew of 3 agents doing 3 tasks, in order:

    Agent 1: Equity Research Analyst --(Task 1: company profiles)--> fundamentals summary
         uses Tool 1: Stock Fundamentals         |
                                                 v
    Agent 2: Portfolio Risk Analyst  --(Task 2: risk check)--------> risk findings
         uses Tool 2: Portfolio Risk Calculator  |
                                                 v
    Agent 3: Investment Report Writer --(Task 3: final report)-----> output/portfolio_xray_report.md
         uses no tools (only writes)

WHAT PROBLEM DOES IT SOLVE?
---------------------------
The question: "Is this portfolio as diversified as it looks?"
The sample investor holds 5 stocks: HDFC Bank, ICICI Bank, Kotak Bank,
TCS and Infosys. On paper that is 5 companies. In reality, 3 are private
banks and 2 are IT services firms. Stocks in the same sector usually rise
and fall on the same days, so the portfolio is closer to 2 bets than 5.
The crew finds this using real price data and explains it in plain language.

HOW TO RUN
----------
    1. pip install -r requirements.txt
    2. Create a file named .env next to this file containing:
           OPENAI_API_KEY=sk-...your key...
    3. python crew.py
    (Optional) change PORTFOLIO below to test your own stocks.

EXPECTED OUTPUT
---------------
    - The terminal shows each agent thinking, calling its tool, and answering.
    - The final report is printed and saved to output/portfolio_xray_report.md.
      It should say the 5 stocks form about 2 groups, show volatility, worst
      drop, beta, and list which sectors are missing.
    - Exact numbers change every day because the prices are live.
==============================================================================
"""

# ---------------------------------------------------------------- IMPORTS ---
import os  # Reads environment variables such as OPENAI_API_KEY and OPENAI_MODEL
from pathlib import Path  # Builds file paths that work on Mac, Windows and Linux

from crewai import LLM, Agent, Crew, Process, Task  # The 5 CrewAI building blocks: model, worker, team, run order, job
from dotenv import load_dotenv  # Loads the key=value lines from the .env file into environment variables

from portfolio_tools import PortfolioRiskTool, StockFundamentalsTool  # Our two custom tools from portfolio_tools.py

# ---------------------------------------------------------------- SETUP -----
load_dotenv()  # Read .env so OPENAI_API_KEY is available; CrewAI picks it up automatically

OUTPUT_DIR = Path(__file__).parent / "output"  # Folder for the final report, next to this file
OUTPUT_DIR.mkdir(exist_ok=True)  # Create it if it does not exist yet

PORTFOLIO = {  # The investor's holdings: ticker -> share of money. Change these to test any portfolio.
    "HDFCBANK.NS": 0.25,  # 25% in HDFC Bank
    "ICICIBANK.NS": 0.20,  # 20% in ICICI Bank
    "KOTAKBANK.NS": 0.15,  # 15% in Kotak Mahindra Bank
    "TCS.NS": 0.20,  # 20% in Tata Consultancy Services
    "INFY.NS": 0.20,  # 20% in Infosys
}

llm = LLM(  # One LLM shared by all three agents
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),  # Model from .env if set, otherwise gpt-4o-mini (cheap and good with tools)
    temperature=0,  # 0 = least random, so every student gets a similar answer
)


# ---------------------------------------------------------------- AGENTS ----
# An Agent = role (job title) + goal (what it wants) + backstory (how it behaves) + tools + llm.

research_analyst = Agent(
    role="Equity Research Analyst",  # Job title
    goal="Describe each company in the portfolio accurately using live market data.",  # What success looks like
    backstory=(  # Behaviour instructions
        "You cover Indian listed companies. You only report numbers that come from the Stock "
        "Fundamentals tool, and you always note which sector each company belongs to."
    ),
    tools=[StockFundamentalsTool()],  # Tool 1 only
    llm=llm,  # Which model powers this agent
    allow_delegation=False,  # Cannot hand work to another agent; keeps the flow easy to follow
    verbose=True,  # Print this agent's steps so the class can watch it work
)

risk_analyst = Agent(
    role="Portfolio Risk Analyst",  # Job title
    goal="Measure how risky the portfolio really is and find stocks that rise and fall together.",  # What success looks like
    backstory=(  # Behaviour instructions: always use the tool for maths
        "You never calculate statistics yourself. You always call the Portfolio Risk Calculator "
        "and base every statement on its output."
    ),
    tools=[PortfolioRiskTool()],  # Tool 2 only
    llm=llm,
    allow_delegation=False,
    verbose=True,
)

report_writer = Agent(
    role="Investment Report Writer",  # Job title
    goal="Explain the findings to a beginner investor in simple language, with no jargon left unexplained.",  # What success looks like
    backstory=(  # Behaviour instructions: plain language, exact numbers, no stock tips
        "You write for people who have never studied finance. You use short sentences, keep every "
        "number exactly as given, and never recommend buying or selling a specific stock."
    ),
    tools=[],  # No tools: this agent only writes
    llm=llm,
    allow_delegation=False,
    verbose=True,
)


# ---------------------------------------------------------------- TASKS -----
# A Task = description (instructions) + expected_output (what the answer must look like) + agent.
# {tickers} and {weights} are filled in from the inputs passed to crew.kickoff() at the bottom.

fundamentals_task = Task(
    description=(
        "Call the Stock Fundamentals tool for these tickers: {tickers}.\n"
        "Summarise each company in one line, then count how many stocks belong to each sector."
    ),
    expected_output=(
        "A table with ticker, company, sector, price, P/E, market cap and 1-year return, "
        "followed by a sector count, e.g. 'Financial Services: 3, Technology: 2'."
    ),
    agent=research_analyst,  # Agent 1 does this task
)

risk_task = Task(
    description=(
        "Call the Portfolio Risk Calculator ONCE with tickers {tickers} and weights {weights} "
        "(same order). Then explain each result in one simple sentence: volatility, max drawdown, "
        "1-year return vs Nifty, beta, the pairs that move together, and the hidden groups. "
        "Link each hidden group to the sectors found in the previous task."
    ),
    expected_output=(
        "The full tool report exactly as returned, then a numbered plain-language explanation of each "
        "result, ending with one sentence answering: is this portfolio truly diversified?"
    ),
    agent=risk_analyst,  # Agent 2 does this task
    context=[fundamentals_task],  # Gets Task 1's output (needed to link groups to sectors)
)

report_task = Task(
    description=(
        "Write a 'Portfolio X-Ray' report for the investor using the two previous outputs. Sections:\n"
        "1. The verdict in one sentence (how many stocks vs how many real groups).\n"
        "2. What you own: a short table of the companies and sectors.\n"
        "3. How risky it is: volatility, worst drop and beta, each explained in plain words.\n"
        "4. The hidden concentration: which stocks move together and what % of money each group holds.\n"
        "5. Sectors missing from the portfolio (name sectors only, not specific stocks).\n"
        "End with: 'This report is for learning only and is not investment advice.'"
    ),
    expected_output="A Markdown report under 450 words with the five sections above and the closing line.",
    agent=report_writer,  # Agent 3 does this task
    context=[fundamentals_task, risk_task],  # Needs both earlier outputs
    output_file="output/portfolio_xray_report.md",  # Relative path: CrewAI turns absolute paths into relative ones
)


# ---------------------------------------------------------------- CREW ------
crew = Crew(
    agents=[research_analyst, risk_analyst, report_writer],  # The team
    tasks=[fundamentals_task, risk_task, report_task],  # The jobs, in run order
    process=Process.sequential,  # One task after another; each output is available to later tasks
    verbose=True,  # Print the crew's progress
)


# ---------------------------------------------------------------- RUN -------
if __name__ == "__main__":  # Only run the crew when this file is executed directly
    result = crew.kickoff(  # Start the crew; returns once all three tasks are done
        inputs={  # These values replace {tickers} and {weights} in the task descriptions
            "tickers": list(PORTFOLIO.keys()),  # ['HDFCBANK.NS', 'ICICIBANK.NS', ...]
            "weights": list(PORTFOLIO.values()),  # [0.25, 0.20, ...] in the same order
        }
    )

    print("\n" + "=" * 70)  # Separator so the final answer is easy to find
    print("PORTFOLIO X-RAY REPORT")
    print("=" * 70)
    print(result.raw)  # .raw is the plain text of the last task's output (the report)
    print(f"\nSaved to: {OUTPUT_DIR / 'portfolio_xray_report.md'}")  # Where the file is