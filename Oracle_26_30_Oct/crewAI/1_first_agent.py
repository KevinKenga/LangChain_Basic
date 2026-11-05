'''
blog writer agent

'''

import os
from dotenv import load_dotenv
load_dotenv()
from crewai import Agent, Task , Crew
from crewai_tools import WebsiteSearchTool

# create the tool object
search_tool = WebsiteSearchTool()

# create the agent object
writer_agent = Agent(
    role = "Blog Writer Agent",
    goal = "Write short, clear blog posts for social media, based on teh latest research on the topic ",
    backstory = "You can explain complex concepts, with ease and simple analogies",
    llm = "gpt-4o-mini",
    tools = [search_tool]
)

# define the task
write_task = Task(
    description = "Write a 350 word blog post about the {topic}",
    expected_output = "A 350 word blog post about the {topic} for Linkedin, with clickable title, and 4 paragraphs",
    agent = writer_agent
)

# assemble the crew
crew = Crew(
    agents = [writer_agent],
    tasks = [write_task],
    verbose = True
)

# execute 
result = crew.kickoff(inputs = {"topic": "Latest investments by Oracle in 2026"})

print(result)