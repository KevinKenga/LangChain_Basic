"""
Shared helper functions used by embeddding_docs.py, embedding_query.py,
similarity_search.py and rag_chat.py.

Why this file exists:
Both embeddding_docs.py and embedding_query.py used to each have their own
copy of the exact same "read a file / ask the user for text" functions.
That's duplicate code - if we ever need to fix a bug in file reading, we'd
have to fix it in multiple places. Pulling the shared logic into one file
(this one) means every script can `import` it and there is only one copy
to maintain.
"""
import json


def read_pdf_text(path):
    """Extract all text from a PDF using pypdf (optional dependency)."""
    from pypdf import PdfReader  # imported here so this module still loads
                                  # even without pypdf installed, unless this path is used
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_excel_text(path):
    """Extract all cell values from an Excel file using openpyxl (optional
    dependency). Excel files are a zipped binary format, so they can't be
    opened as plain text like a .txt/.md file."""
    from openpyxl import load_workbook
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
    (optional dependency). Old .doc files use a different, older binary
    format that python-docx can't read - only .docx is supported."""
    from docx import Document
    document = Document(path)
    return "\n".join(p.text for p in document.paragraphs if p.text)


# Safety cap on how much text we'll ever try to read/embed in one go.
# Why: a plain-text/CSV read loads the WHOLE file into memory as one giant
# string, and embedding it means sending that text (split into chunks) to
# OpenAI's API - one call per chunk. A small multi-page PDF is a few dozen
# KB and is totally fine. A 600 MB CSV with millions of rows would hang
# Python reading it, and would turn into hundreds of thousands of paid API
# calls if we tried to chunk + embed all of it. 2 MB is generous for a
# learning exercise (that's already a lot of PDF/Word pages) while blocking
# accidentally picking a huge dataset file.
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB


def read_file_text(path):
    """Read any supported file type and return its contents as a single
    string:
      - .pdf          -> pypdf
      - .xlsx / .xls  -> openpyxl (Excel)
      - .docx         -> python-docx (Word; old .doc is not supported)
      - everything else (.txt, .md, .csv, ...) -> read as plain text.

    Raises a clear error instead of hanging/crashing if the file is way
    bigger than what this learning exercise is meant to handle."""
    import os
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"'{path}' is {size / 1024 / 1024:.1f} MB, which is over the "
            f"{MAX_FILE_BYTES / 1024 / 1024:.0f} MB limit for this exercise. "
            "Large datasets (e.g. a multi-million-row CSV) aren't a good fit "
            "for embedding one row/file at a time - that's hundreds of "
            "thousands of paid API calls. Pick a smaller file, or paste just "
            "a sample/snippet of the text instead (option [1])."
        )

    lower = path.lower()
    if lower.endswith(".pdf"):
        return read_pdf_text(path)
    if lower.endswith((".xlsx", ".xls")):
        return read_excel_text(path)
    if lower.endswith(".docx"):
        return read_word_text(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def pick_file_with_dialog(title="Select a file"):
    """Open a native 'choose file' window so the user can click/navigate
    instead of typing a path. Uses tkinter, which ships with Python, but a
    few Python installs don't have the Tk GUI pieces - if that happens we
    fall back to asking for the path as text (handled by the caller)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(title=title)
    root.destroy()
    return path or None


def chunk_text(text, chunk_size=1000, overlap=100):
    """Split a long piece of text into smaller overlapping chunks.

    Why: OpenAI's embedding models reject text over a certain length
    (~8,191 tokens, roughly 6,000 words). A multi-page PDF/Word document can
    easily be longer than that, so instead of sending the whole thing in one
    call (which would error out), we cut it into chunk_size-character pieces.

    `overlap` repeats the last N characters of one chunk at the start of the
    next one, so a sentence/idea that happens to fall right on a chunk
    boundary doesn't get split in a way that loses its meaning.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap  # step back by `overlap` so chunks share some text
    return chunks


def get_text_from_user(prompt_label="text"):
    """Ask the user to either type/paste text, or pick a file, and return
    the resulting text as a single string. Used for single-item input
    (a query, a chat question, ...)."""
    choice = input(
        f"How do you want to provide your {prompt_label}?\n"
        "  [1] Type/paste text\n"
        "  [2] Load from a file - opens a window to click/navigate/select\n"
        "Enter 1 or 2: "
    ).strip()

    if choice == "2":
        file_path = pick_file_with_dialog(title=f"Select a file with your {prompt_label}")
        if not file_path:
            file_path = input("Enter the full path to your file: ").strip().strip('"')
        print(f"Selected file: {file_path}")
        try:
            return read_file_text(file_path)
        except ValueError as error:
            # e.g. file too large - show the friendly message instead of a
            # raw crash/traceback.
            print(f"\nCould not use that file: {error}\n")
            raise SystemExit(1)

    print("Type or paste your text. When finished, type END on its own line:")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def get_documents_from_user():
    """Same idea as get_text_from_user, but splits the result into chunks
    with chunk_text() and returns them as a list (embed_documents() expects
    a list; multiple chunks means a long file becomes several separate
    "documents" instead of one oversized one)."""
    text = get_text_from_user(prompt_label="document(s)")
    chunks = chunk_text(text)
    if len(chunks) > 1:
        print(f"Text was split into {len(chunks)} chunks for embedding.")
    return chunks


def cosine_similarity(vec_a, vec_b):
    """How similar two embedding vectors are, from -1 (opposite) to 1
    (identical direction). This is the standard way to compare embeddings.
    Written with plain Python (no numpy) since this project doesn't need
    numpy for anything else."""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = sum(a * a for a in vec_a) ** 0.5
    magnitude_b = sum(b * b for b in vec_b) ** 0.5
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    return dot_product / (magnitude_a * magnitude_b)


def save_embeddings(path, documents, vectors):
    """Persist documents + their embedding vectors to a JSON file, so a
    later script (similarity_search.py, rag_chat.py) can load them back
    without paying to re-embed the same text again."""
    records = [{"text": doc, "embedding": vec} for doc, vec in zip(documents, vectors)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f)
    print(f"Saved {len(records)} embedded document(s) to {path}")


def load_embeddings(path):
    """Load documents + embedding vectors previously saved by
    save_embeddings(). Returns a list of {"text": ..., "embedding": ...}."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
