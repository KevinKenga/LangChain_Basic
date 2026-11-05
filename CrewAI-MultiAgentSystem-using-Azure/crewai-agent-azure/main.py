"""
Main Entry Point.
Runs the Crew -> Uploads to Blob Storage -> Saves to PostgreSQL.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Check Config
if not os.getenv("OPENAI_API_KEY") or not os.getenv("FIRECRAWL_API_KEY"):
    print("❌ Error: Missing API Keys in .env")
    sys.exit(1)

# Imports
try:
    from src.agents.crew import run_financial_crew
    from src.shared.storage import StorageService
    from src.shared.database import DatabaseService
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)

def main():
    print("==================================================")
    print("      💸 AI Financial Analyst Crew (Production)   ")
    print("==================================================")
    
    ticker = input("\nEnter a stock ticker (e.g., MSFT): ").strip().upper()
    if not ticker: return

    try:
        # 1. Run AI
        # 'result_object' is a complex CrewOutput object (contains token usage, tasks, etc.)
        result_object = run_financial_crew(ticker)
        
        # ---------------------------------------------------------
        # FIX: Extract the raw text string from the object
        # ---------------------------------------------------------
        final_report_text = str(result_object)
        
        print("\n... [Analysis Complete] ...\n")
        print(final_report_text) # Print the text to console
        
        # 2. Upload File to Blob Storage
        filename = f"investment_report_{ticker}.md"
        storage = StorageService()
        
        print(f"\n☁️  Uploading {filename} to Azure Blob Storage...")
        # We upload the local file that CrewAI created automatically
        url = storage.upload_file(filename, filename)
        print(f"✅ Blob Storage URL: {url}")
        
        # 3. Save Record to PostgreSQL
        print(f"🗄️  Saving to Azure PostgreSQL...")
        db = DatabaseService()
        
        # FIX: Pass 'final_report_text' (string), NOT 'result_object'
        db.save_report(ticker=ticker, content=final_report_text)
        
        print("\n✅ Success! Pipeline Finished.")
        
    except Exception as e:
        print(f"\nFailed: {str(e)}")

if __name__ == "__main__":
    main()