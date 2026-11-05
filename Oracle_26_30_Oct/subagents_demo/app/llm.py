"""
=====================================================================
FILE: app/llm.py
=====================================================================
PURPOSE
    One small helper that sends a system prompt + user message to the
    LLM and returns the reply text. The supervisor and all 3 subagents
    use it.

WHAT PROBLEM IT SOLVES
    Keeps the OpenAI setup in one place, so the agent files only show
    agent logic.

HOW TO RUN
    Not run directly. Imported as:  from app.llm import call_llm

EXPECTED OUTPUT
    None (it only defines a function).
=====================================================================
"""

# os reads environment variables such as OPENAI_API_KEY.
import os

# load_dotenv copies values from the .env file into the environment.
from dotenv import load_dotenv

# OpenAI client for chat completions.
from openai import OpenAI


# Read .env so OPENAI_API_KEY is available.
load_dotenv()

# Model name; can be changed in .env.
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Create the client once; it reads OPENAI_API_KEY from the environment.
client = OpenAI()


def call_llm(system: str, user: str) -> str:
    """Send one request and return the reply text."""
    # One chat call. temperature=0 gives repeatable output for class demos.
    response = client.chat.completions.create(
        # Which model to use.
        model=MODEL,
        # Same input -> same output.
        temperature=0,
        # system = the agent's role; user = its task and data.
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    # Return only the text of the reply.
    return response.choices[0].message.content
