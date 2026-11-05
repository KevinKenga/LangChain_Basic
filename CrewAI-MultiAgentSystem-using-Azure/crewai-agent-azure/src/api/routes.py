'''
Build the Endpoint (src/api/routes.py)
This is the "Controller." It receives the request, calls the AI agents 
(just like your CLI script did), and returns the JSON result.

'''

"""
API Routes.
Handles the incoming HTTP requests and triggers the AI Crew.
"""
from fastapi import APIRouter, HTTPException
from src.api.models import AnalysisRequest, AnalysisResponse
from src.agents.crew import run_financial_crew
from src.shared.storage import StorageService
from src.shared.database import DatabaseService

# Create a router to organize our endpoints
router = APIRouter()

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_stock(request: AnalysisRequest):
    """
    Triggers the Financial Analysis Crew for a given ticker.
    1. Runs the Agents.
    2. Uploads report to Azure Blob.
    3. Saves record to Azure Postgres.
    """
    ticker = request.ticker.upper()
    
    try:
        # 1. Run the AI Crew
        print(f"🚀 API Request received for: {ticker}")
        result_object = run_financial_crew(ticker)
        
        # Convert CrewOutput to String (Crucial fix from before)
        report_text = str(result_object)

        # 2. Upload to Blob Storage
        filename = f"investment_report_{ticker}.md"
        storage = StorageService()
        # Note: CrewAI saved the file locally; we just push it.
        blob_url = storage.upload_file(filename, filename)

        # 3. Save to Database
        db = DatabaseService()
        db.save_report(ticker=ticker, content=report_text)

        return AnalysisResponse(
            status="success",
            ticker=ticker,
            report_content=report_text,
            report_url=blob_url,
            message="Analysis complete and saved to cloud."
        )

    except Exception as e:
        print(f"❌ API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))