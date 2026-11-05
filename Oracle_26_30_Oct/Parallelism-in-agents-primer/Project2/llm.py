"""The GPT-4o call used by every judge, kept apart from the graph logic.
Put your key in a .env file next to run.py:  OPENAI_API_KEY=sk-...
"""
from dotenv import load_dotenv
load_dotenv()  # reads the .env file and puts OPENAI_API_KEY into the environment

from openai import OpenAI

client = OpenAI()  # picks up OPENAI_API_KEY from the environment
MODEL = "gpt-4o"


def classify_email(email: str, persona: str):
    """One judge's opinion, seen through its own `persona` (its lens).

    Temperature is LOW on purpose. The disagreement between judges now comes from
    their different personas, not from randomness — so a split vote is reliable,
    not luck. Returns the vote, a confidence score (0-100), and a short reason.
    """
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        messages=[
            {"role": "system", "content":
                f"{persona}\n\n"
                "Reply in this EXACT format:\n"
                "VOTE | CONFIDENCE | REASON\n"
                "VOTE is SPAM or NOT_SPAM. CONFIDENCE is a number 0-100. "
                "REASON is under 10 words."},
            {"role": "user", "content": email},
        ],
    )
    return _parse(resp.choices[0].message.content.strip())


def _parse(raw: str):
    """Turn 'SPAM | 80 | classic promo with urgency' into clean parts.
    Falls back gracefully if the model doesn't follow the format exactly.
    """
    parts = [p.strip() for p in raw.split("|")]

    label = parts[0].upper() if parts else ""
    vote = "SPAM" if "SPAM" in label and "NOT" not in label else "NOT_SPAM"

    try:
        digits = "".join(c for c in parts[1] if c.isdigit())
        confidence = max(0, min(100, int(digits)))
    except (IndexError, ValueError):
        confidence = 50

    reason = parts[2] if len(parts) > 2 else ""
    return vote, confidence, reason