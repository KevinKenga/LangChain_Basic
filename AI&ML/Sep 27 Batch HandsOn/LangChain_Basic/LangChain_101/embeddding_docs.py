from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(override=True)
import os
from embedding_utils import get_documents_from_user, save_embeddings
api_key = os.getenv("OPENAI_API_KEY")

# NOTE: model + dimensions must be IDENTICAL to embedding_query.py.
# Similarity search compares a document vector to a query vector - that
# only makes sense if both were produced by the same model/size. (This
# used to be text-embedding-3-large / 50 here, which did NOT match
# embedding_query.py's text-embedding-3-small / 150 - fixed so
# similarity_search.py and rag_chat.py can compare them correctly.)
embedding = OpenAIEmbeddings(
    model = "text-embedding-3-small",
    dimensions = 150,
    api_key = api_key
)

# ============================================================
# KEVIN'S ORIGINAL SECTION (kept as-is for reference/learning).
# This is a hardcoded list of 3 sample documents about Oracle.
# Not executed anymore (see interactive section below instead) -
# uncomment the block below any time you want to go back to it.
# ============================================================
# documents = [
#     """
#     Oracle Corporation is one of the world's largest enterprise software companies,
#     founded in 1977 by Larry Ellison, Bob Miner, and Ed Oates. The company is best
#     known for its relational database management systems, which power mission-critical
#     applications for businesses across industries. Over the years, Oracle has expanded
#     its portfolio to include cloud computing, enterprise resource planning (ERP),
#     customer relationship management (CRM), and supply chain management solutions.
#     Today, Oracle serves thousands of organizations globally, helping them manage
#     data, automate processes, and improve business decision-making.
#     """,
#
#     """
#     Oracle Cloud Infrastructure (OCI) is the company's cloud computing platform,
#     designed to provide scalable, secure, and high-performance cloud services.
#     OCI offers services across computing, storage, networking, databases, analytics,
#     artificial intelligence, and machine learning. Organizations use OCI to modernize
#     legacy applications, run data-intensive workloads, and accelerate digital
#     transformation initiatives. Oracle's cloud strategy emphasizes performance,
#     security, and cost efficiency, making it a competitive alternative to other
#     major cloud providers.
#     """,
#
#     """
#     In recent years, Oracle has invested heavily in artificial intelligence and
#     autonomous technologies. Products such as the Autonomous Database automate
#     routine administrative tasks like patching, tuning, and backups, reducing
#     operational overhead for organizations. Oracle has also integrated generative
#     AI capabilities into its business applications, enabling users to automate
#     workflows, generate insights, and enhance productivity. These innovations
#     position Oracle as a key player in the rapidly evolving enterprise AI landscape.
#     """
# ]
#
# result = embedding.embed_documents(documents)
# print(f"Length of embedding vector for each document: {[len(vec) for vec in result]}")
# print(result)


# ============================================================
# ADDED SECTION (learning notes below) - interactive version.
# Goal: instead of hardcoding the documents, ask the user at
# run time for EITHER pasted text OR a file to embed.
# ============================================================
#
# How it works, step by step:
# 1. Ask the user to choose: type/paste text, or give a file path.
# 2. If "type": read multiple paragraphs from the keyboard. Since
#    a document can span several lines, we keep reading lines
#    until the user types a line that just says "END" - that is
#    our simple "stop signal". Blank lines are allowed inside a
#    document (useful for multi-paragraph text).
# 3. If "file": read the file's contents as one document. We
#    support plain text (.txt, .md, etc.) with the standard
#    library, and .pdf via pypdf if it is installed (optional,
#    so this script still runs even without pypdf).
# 4. Either way we end up with a list of one or more documents,
#    exactly like Kevin's original `documents` list above, and
#    reuse the exact same `embedding.embed_documents(...)` call.

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
    path = filedialog.askopenfilename(title="Select a document to embed")
    root.destroy()
    return path or None       # empty string if the user cancels


def get_documents_from_user():
    choice = input(
        "How do you want to provide your document(s)?\n"
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
        return [read_file_text(file_path)]

    # choice == "1" (or anything else): read pasted/typed text from the keyboard
    print("Type or paste your document. When finished, type END on its own line:")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return ["\n".join(lines)]


if __name__ == "__main__":
    documents = get_documents_from_user()
    result = embedding.embed_documents(documents)
    print(f"Number of documents embedded: {len(documents)}")
    print(f"Length of embedding vector for each document: {[len(vec) for vec in result]}")
    print(result)