'''
2 agents ; 
1 : searches the website
2 : writes a blog post based on the search results

'''
from dotenv import load_dotenv
load_dotenv()
from crewai import Agent, Task , Crew, Process
from crewai_tools import WebsiteSearchTool


# create the tool object
WEBSITE = "https://www.oracle.com/news/"
search_tool = WebsiteSearchTool(website=WEBSITE)

# create the researcher agent object
researcher_agent = Agent(
    role = "Website Researcher Agent",
    goal = "Search the website for relevant information on the {topic}, form the website",
    backstory = "You only report what you find on website, and do not make up information. \
        You are a researcher, not a writer",
    tools = [search_tool],
    llm = "gpt-4o-mini",
)

# define writer agent 
writer_agent = Agent(
    role = "Blog writer",
    goal ="Turn the research notes from the website agent , into a clear post for social media",
    backstory= "You write short, clear blog posts, and explain complex concepts, with ease and simple analogies",
    llm = "gpt-4o-mini",
)

# define the task for the researcher agent
research_task = Task(
    description="Search the website for relevant information on the {topic}, \
        and summarize the key points in a clear and concise manner",
    expected_output="8-10 bullet points from the website, relevant to the {topic}",
    agent = researcher_agent
)

# define the task for the writer agent
writer_task = Task(
    description="Write a clear and concise 300 word blog post based on the research notes from the website agent",
    expected_output="A well-structured blog post explaining the {topic} with simple analogies , and conclusion, \
        in 4 paragraphs, with a clickable title",
    agent = writer_agent,
    context = [research_task],
    output_file = "blog_post.md"
)

# assemble the crew
crew = Crew(
    agents = [researcher_agent, writer_agent],
    tasks = [research_task, writer_task],
    process = Process.sequential,
    verbose = True
)

result = crew.kickoff(inputs = {"topic": "extract the latest news on google TPUs"})

print(result)