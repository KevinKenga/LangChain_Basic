"""All OpenAI calls live here, kept apart from the graph logic.
Set your key first:  export OPENAI_API_KEY=sk-...
"""
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from the environment
MODEL = "gpt-4o"


def summarize_text(text: str) -> str:
    """Summarize one document in two sentences."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Summarize the text in exactly two sentences."},
            {"role": "user", "content": text},
        ],
    )
    return resp.choices[0].message.content.strip()


def make_digest(summaries: list[str]) -> str:
    """Combine several summaries into one short digest."""
    joined = "\n".join(f"- {s}" for s in summaries)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Combine these summaries into one short digest of 3-4 sentences."},
            {"role": "user", "content": joined},
        ],
    )
    return resp.choices[0].message.content.strip()