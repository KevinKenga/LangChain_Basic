"""
=====================================================================
FILE: app/subagents.py
=====================================================================
PURPOSE
    The 3 subagents. Each one is a plain function that:
      - receives ONLY a task instruction from the supervisor plus the
        exact data it needs,
      - calls the LLM with its own system prompt,
      - returns its result as text.

        extractor : reads both PDFs  -> key facts from each
        analyst   : key facts        -> matches and gaps
        writer    : matches and gaps -> short decision note

WHAT PROBLEM IT SOLVES
    One agent doing everything gets a long, mixed prompt and makes more
    mistakes. Each subagent here has one job and a small, clean input.
    It never sees the supervisor's conversation or other subagents'
    prompts. That separation is what makes it a subagent.

HOW TO RUN
    Not run directly. Called by app/supervisor.py.

EXPECTED OUTPUT
    Each function returns a string.
=====================================================================
"""

# Path builds the file paths to the PDFs.
from pathlib import Path

# PdfReader extracts text from PDFs.
from pypdf import PdfReader

# Our shared LLM helper.
from app.llm import call_llm


# Folder that holds the 2 input PDFs.
PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"


def read_pdf(filename: str) -> str:
    """Return all text from one PDF."""
    # Open the PDF.
    reader = PdfReader(PDF_DIR / filename)
    # Join the text of every page with a newline.
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extractor(instruction: str) -> str:
    """Subagent 1: read both PDFs and pull out the key facts."""
    # This subagent is the only one that opens the PDFs.
    jd_text = read_pdf("job_description.pdf")
    # Read the resume.
    resume_text = read_pdf("candidate_resume.pdf")
    # Its own role. It knows nothing about the analyst or writer.
    system = (
        "You are a document extraction agent. Extract facts only, no opinions. "
        "Output two sections: 'JOB' (must-have skills, good-to-have skills, years needed, budget, notice period) "
        "and 'CANDIDATE' (skills, years of experience, notice period, key achievements)."
    )
    # Task from the supervisor + the raw documents.
    user = f"Task: {instruction}\n\nJOB DESCRIPTION:\n{jd_text}\n\nRESUME:\n{resume_text}"
    # Ask the LLM and return the facts.
    return call_llm(system, user)


def analyst(instruction: str, facts: str) -> str:
    """Subagent 2: compare job facts with candidate facts."""
    # Its own role. It gets the extracted facts, never the raw PDFs.
    system = (
        "You are a hiring analyst agent. Compare the JOB and CANDIDATE facts. "
        "Output: 'MATCHES' (bullet list), 'GAPS' (bullet list), and 'FIT SCORE: N/10' with one line of reason."
    )
    # Task from the supervisor + only the facts.
    user = f"Task: {instruction}\n\nFACTS:\n{facts}"
    # Ask the LLM and return the analysis.
    return call_llm(system, user)


def writer(instruction: str, analysis: str) -> str:
    """Subagent 3: write the decision note for the hiring manager."""
    # Its own role. It gets only the analysis.
    system = (
        "You are a recruiter writing agent. Write a note of at most 120 words for the hiring manager. "
        "Start with 'Decision: Shortlist' or 'Decision: Reject'. Mention the top 2 strengths, "
        "the main gap, and one question to ask in the interview."
    )
    # Task from the supervisor + only the analysis.
    user = f"Task: {instruction}\n\nANALYSIS:\n{analysis}"
    # Ask the LLM and return the note.
    return call_llm(system, user)
