"""
Web Scraping & Sentiment Extraction Module.

This module integrates the Firecrawl API (via firecrawl-py) to act as the 
system's "Eyes" on the internet. It searches for qualitative data—news, 
analyst opinions, and market rumors—that purely quantitative tools miss.

Classes:
    SentimentSearchTool: Searches the web for recent news articles.

Dependencies:
    - firecrawl-py: For robust scraping and markdown conversion.
    - src.shared.config: For secure API key management.
"""


from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from firecrawl import FirecrawlApp
from src.shared.config import settings

# ==============================================================================
# Input Schemas
# ==============================================================================

class FirecrawlSearchInput(BaseModel):
    """
    Input schema for the SentimentSearchTool.
    """
    query: str = Field(
        ..., 

        description="The search query string (e.g., 'NVDA recent analyst ratings')."
    )

# ==============================================================================
# Tool Definitions
# ==============================================================================

class SentimentSearchTool(BaseTool):
    """
    A CrewAI tool that performs a semantic web search and returns scraped content.
    
    Unlike a standard Google Search which returns only snippets, this tool 
    uses Firecrawl to visit the top results and extract the full page content 
    in Markdown format. This gives the LLM significantly more context.
    """
    
    name: str = "Search Stock News"
    description: str = (
        "Searches the web for the latest news, analyst ratings, and market sentiment "
        "surrounding a specific stock or financial topic. "
        "Returns a summary of the top 3 relevant articles."
    )
    args_schema: Type[BaseModel] = FirecrawlSearchInput

    def _run(self, query: str) -> str:
        """
        Executes the search via Firecrawl.

        Args:
            query (str): The search topic.

        Returns:
            str: A markdown-formatted string containing the scraped content 
                 of the top search results.
        """
        # Ensure API key is present before initialization
        if not settings.firecrawl_api_key:
            return "Error: FIRECRAWL_API_KEY is missing in configuration."

        try:
            app = FirecrawlApp(api_key=settings.firecrawl_api_key)
            
            # Perform the search
            # We limit to 3 results to balance context window usage vs information density.
            # 'formats': ['markdown'] ensures the LLM gets clean text, not messy HTML.
            results = app.search(
                query=query,
                limit=3,
                scrape_options={"formats": ["markdown"]}
            )
            
            
            return str(results)

        except Exception as e:
            return f"Error executing Firecrawl search for query '{query}': {str(e)}"