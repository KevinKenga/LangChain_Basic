import streamlit as st
import requests
import json

# === Configuration ===
# This must match the address and prefix defined in src/api/main.py
API_URL = "http://127.0.0.1:8000/api/v1/analyze"

# === Page Setup ===
st.set_page_config(
    page_title="AI Financial Analyst Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === Custom CSS for polish ===
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
    }
    h1 {
        color: #0066cc;
    }
</style>
""", unsafe_allow_html=True)


# === Main Header ===
st.title("🤖 AI Agent Financial Analyst")
st.markdown(
    """
    Welcome! This tool leverages a **multi-agent AI team** (powered by CrewAI) to perform 
    comprehensive financial research on a given stock ticker.
    
    It fetches live data, analyzes market sentiment, and generates a professional investment report, 
    saving everything to **Azure Cloud**.
    """
)
st.divider()

# === Sidebar: Input & Controls ===
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # Ticker Input
    ticker_input = st.text_input(
        "Enter Stock Ticker Symbol",
        value="",
        placeholder="e.g., NVDA, MSFT, TSLA",
        max_chars=5,
        help="Enter the standard ticker symbol for the company you want to analyze."
    ).upper().strip()
    
    # Run Button
    run_button = st.button("🚀 Run Full Analysis", type="primary")
    
    st.markdown("---")
    st.info(
        "**Note:** A full analysis typically takes 1-3 minutes depending on the complexity of the research."
    )

# === Main App Logic ===

# Handle Button Click
if run_button:
    if not ticker_input:
        st.error("⚠️ Please enter a ticker symbol before running the analysis.")
    else:
        # Clear previous results
        if 'analysis_result' in st.session_state:
            del st.session_state['analysis_result']
            
        with st.spinner(f"🧠 AI Agents are researching '{ticker_input}'... Please hold..."):
            try:
                # Send POST request to FastAPI Backend
                payload = {"ticker": ticker_input}
                response = requests.post(API_URL, json=payload, timeout=300) # 5 min timeout
                
                # Check for successful response
                if response.status_code == 200:
                    data = response.json()
                    # Store result in session state for persistence
                    st.session_state['analysis_result'] = data
                    st.success(f"✅ Analysis for {ticker_input} complete!")
                else:
                    st.error(f"❌ Analysis Failed. Status Code: {response.status_code}")
                    try:
                        error_detail = response.json().get('detail', response.text)
                        st.error(f"Error Details: {error_detail}")
                    except:
                        st.error(f"Raw Response: {response.text}")
                        
            except requests.exceptions.ConnectionError:
                 st.error("🚨 **Connection Error:** Could not connect to the backend API.")
                 st.warning("Is the FastAPI server running? (Check Terminal 1)")
            except requests.exceptions.Timeout:
                 st.error("⏰ **Timeout Error:** The analysis took too long and timed out.")
            except Exception as e:
                 st.error(f"An unexpected error occurred: {e}")


# Display Results (if present in session state)
if 'analysis_result' in st.session_state:
    data = st.session_state['analysis_result']
    ticker_name = data.get("ticker", ticker_input)
    
    # 1. Report Tab View
    tab1, tab2 = st.tabs(["📄 Final Investment Report", "🔍 Metadata & Logs"])
    
    with tab1:
        st.subheader(f"Investment Analysis: {ticker_name}")
        # Display the Markdown report content
        report_content = data.get("report_content", "*No report content found.*")
        st.markdown(report_content)
        
        st.divider()
        
        # Download Button
        st.download_button(
            label="📥 Download Report as Markdown",
            data=report_content,
            file_name=f"{ticker_name}_Investment_Report.md",
            mime="text/markdown"
        )

    with tab2:
        st.subheader("Backend Execution Details")
        # Display links and raw JSON data
        st.markdown(f"**Azure Blob Storage URL:** [Link to File]({data.get('report_url', '#')})")
        st.markdown(f"**Status:** {data.get('status')}")
        st.markdown(f"**Message:** {data.get('message')}")
        
        with st.expander("See Raw API Response (JSON)"):
            st.json(data)

'''
How to Run the Full Application
To run the complete system, you need two separate terminal windows running at the same time. One for the Backend (Brain) and one for the Frontend (Face).

Terminal 1: Start the Backend API
This starts the FastAPI server that the AI agents live on.

# Make sure you are in the root project folder

uv run uvicorn src.api.main:app --reload

Wait until you see "Application startup complete" and "Uvicorn running on http://127.0.0.1:8000".


Terminal 2: Start the Streamlit Frontend
Open a new terminal window, navigate to your project folder, and run this command to start the UI.

# Make sure you are in the root project folder: 

uv run streamlit run src/frontend/app.py

Access the App
Streamlit will automatically open your default web browser to the app URL, which is usually:

http://localhost:8501

You can now enter a ticker like "NVDA" in the sidebar and click "Run Full Analysis". Watch your terminals to see the logs as the agents work!
'''