'''
OpenAIEmbeddings()

'''
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(override=True)
import os
from embedding_utils import get_text_from_user
api_key = os.getenv("OPENAI_API_KEY")

embedding = OpenAIEmbeddings(
    model = "text-embedding-3-small",
    dimensions = 150,
    api_key = api_key
)

# ============================================================
# KEVIN'S ORIGINAL SECTION (kept as-is for reference/learning).
# This is a hardcoded query string.
# Not executed anymore (see interactive section below instead) -
# uncomment the block below any time you want to go back to it.
# ============================================================
# text = "There are three built-in styles: **default** (balanced, explains as it goes), \
#         **concise** (only the code and a line or two) and **explanatory** \
#         (teaches while it works, useful for people new to the code)."
#
# embedding_vec = embedding.embed_query(text)
# print(embedding_vec)
# print(f"Length of embedding vector: {len(embedding_vec)}")


# ============================================================
# ADDED SECTION (learning notes below) - interactive version.
# Goal: instead of hardcoding the query text, ask the user at
# run time for EITHER typed/pasted text OR a file to embed.
# Note: embed_query() is meant for a single short piece of text
# (e.g. a search question), so unlike embeddding_docs.py we read
# just one block of input here rather than a list of documents.
# ============================================================
#
# How it works, step by step:
# 1. Ask the user to choose: type/paste text, or give a file path.
# 2. If "type": read a single line (or multiple lines ending with
#    "END", same convention as embeddding_docs.py) from the keyboard.
# 3. If "file": read the whole file as the query text. Supports
#    plain text files directly, and .pdf via pypdf if installed.
# 4. Call the exact same `embedding.embed_query(...)` as before.

# NOTE: the file-reading / "ask the user" helper functions that used to be
# defined here moved to embedding_utils.py - embeddding_docs.py needed the
# exact same functions, so keeping one shared copy avoids duplicate code.

if __name__ == "__main__":
    text = get_text_from_user(prompt_label="query text")
    embedding_vec = embedding.embed_query(text)
    print(embedding_vec)
    print(f"Length of embedding vector: {len(embedding_vec)}")