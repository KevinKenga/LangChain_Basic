import os
from dotenv import load_dotenv
load_dotenv(override=True)
from crewai import Agent, Task ,Crew, Process
from stock_tool import get_stock_price

# 1st agent
analyst = Agent(
    role ="Stock Analyst",
    goal ="Collect the latest stock price and 1 month change for each of these stocks: {symbols}",
    backstory = "You are a stock analyst, and you have access to the latest stock prices and historical data. \
        You can provide accurate and up-to-date information on stock performance.",
    tools=[get_stock_price],
    llm = "gpt-4o-mini"
)

# 2nd agent
writer_agent = Agent(
    role = "Stock report  Writer",
    goal = "Write a comprehensive report on the stock performance based on the data provided",
    backstory = "You are a skilled writer with a background in finance and economics. \
        You can translate complex financial data into clear and concise reports.",
    llm = "gpt-4o-mini"
)

# task 1 : 
data_task = Task(
    description="Use the tool to collect the latest share price and 1 month price change for each of these stock symbols: {symbols}. \
        Call the tool once per symbol.",
    expected_output = "One line per symbol with the latest closing price and 1 month price change",
    agent = analyst,
)


# task 2 : 
report_task = Task(
    description ="Write a short report about the share price and 1 month price change of these stock symbols: {symbols}",
    expected_output = "A markdown report with a title, 3 short paragraphs, and a conclusion",
    agent = writer_agent,
    context = [data_task],
    output_file = "stock_report.md",
    
)

crew = Crew(
    agents = [analyst, writer_agent],
    tasks = [data_task, report_task],
    process = Process.sequential,
    verbose = True
)

result = crew.kickoff(inputs = {"symbols": "ORCL, AAPL, MSFT"})
print(result)