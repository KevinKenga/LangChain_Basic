"""
API Data Models.
Defines the structure of Requests and Responses using Pydantic.
"""
from pydantic import BaseModel, Field

class AnalysisRequest(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol (e.g., NVDA, TSLA).")

class AnalysisResponse(BaseModel):
    status: str
    ticker: str
    report_content: str
    report_url: str
    message: str