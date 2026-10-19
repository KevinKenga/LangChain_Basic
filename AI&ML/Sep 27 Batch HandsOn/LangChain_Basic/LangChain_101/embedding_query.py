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

def read_pdf_text(path):
    """Extract all text from a PDF using pypdf (optional dependency)."""
    from pypdf import PdfReader  # imported here so the script works even
                                  # without pypdf installed, unless this path is used
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_excel_text(path):
    """Extract all cell values from an Excel file using openpyxl (optional
    dependency). Excel files are a zipped binary format, so they can't be
    opened as plain text like a .txt/.md file."""
    from openpyxl import load_workbook  # imported here so the script works even
                                         # without openpyxl installed, unless this path is used
    workbook = load_workbook(path, data_only=True, read_only=True)
    lines = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell) for cell in row if cell is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def read_word_text(path):
    """Extract all paragraph text from a Word .docx file using python-docx
    (optional dependency). Like .xlsx, .docx is a zipped binary format, so
    it can't be opened as plain text either. (Old .doc files use a different,
    older binary format that python-docx can't read - only .docx is supported.)"""
    from docx import Document  # imported here so the script works even
                                # without python-docx installed, unless this path is used
    document = Document(path)
    return "\n".join(p.text for p in document.paragraphs if p.text)


def read_file_text(path):
    """Read any supported file type and return its contents as a single
    string:
      - .pdf          -> pypdf
      - .xlsx / .xls  -> openpyxl (Excel)
      - .docx         -> python-docx (Word; old .doc is not supported)
      - everything else (.txt, .md, .csv, ...) -> read as plain text,
        since those formats are already just text under the hood."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        return read_pdf_text(path)
    if lower.endswith((".xlsx", ".xls")):
        return read_excel_text(path)
    if lower.endswith(".docx"):
        return read_word_text(path)
    # plain text file (.txt, .md, .csv, ...); errors="replace" avoids a crash
    # if the file still has a few non-UTF-8 bytes in it
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def pick_file_with_dialog():
    """Open a native macOS 'choose file' window so the user can click/navigate
    instead of typing a path. Uses tkinter, which ships with Python, but a
    few Python installs (e.g. some Homebrew ones) don't have the Tk GUI
    pieces - if that happens we fall back to asking for the path as text."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()          # hide the empty main Tk window, we only want the dialog
    root.attributes("-topmost", True)  # bring the dialog to the front on macOS
    path = filedialog.askopenfilename(title="Select a file with your query text")
    root.destroy()
    return path or None       # empty string if the user cancels


def get_query_text_from_user():
    choice = input(
        "How do you want to provide your query text?\n"
        "  [1] Type/paste text\n"
        "  [2] Load from a file - opens a window to click/navigate/select\n"
        "Enter 1 or 2: "
    ).strip()

    if choice == "2":
        file_path = pick_file_with_dialog()
        if not file_path:
            # tkinter unavailable, or the user closed the dialog without picking
            file_path = input("Enter the full path to your file: ").strip().strip('"')
        print(f"Selected file: {file_path}")
        return read_file_text(file_path)

    # choice == "1" (or anything else): read pasted/typed text from the keyboard
    print("Type or paste your text. When finished, type END on its own line:")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    text = get_query_text_from_user()
    embedding_vec = embedding.embed_query(text)
    print(embedding_vec)
    print(f"Length of embedding vector: {len(embedding_vec)}")