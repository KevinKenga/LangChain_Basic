Understanding of Files
requirement.txt: list of libraries, that I need for this pipeline
then run: source venv/bin/activate
pip install -r requirements.txt
go to .env file. store your APIs Keys, Database Keys

## What this chatbot/LangChain_101 project does

This folder is the first hands-on LangChain exercise. It has 3 small, separate
scripts that each demonstrate one OpenAI capability through LangChain:

- `chat_oi.py` — a basic **chatbot**: sends one prompt to a chat model
  (`gpt-4o` via `ChatOpenAI`) and prints the reply. No memory of previous
  messages yet (each run is a single question/answer).
- `embeddding_docs.py` — turns one or more **documents** into embedding
  vectors (`embedding.embed_documents(...)`), useful for building a search
  index over many pieces of text.
- `embedding_query.py` (also saved as `EMBEDDING_QUERY.PY`) — turns a single
  **search question** into an embedding vector (`embedding.embed_query(...)`),
  so it can later be compared against the document embeddings above to find
  the most relevant match.

Both embedding scripts were upgraded from hardcoded sample text to an
**interactive** flow: when you run them, they ask you to either type/paste
text, or open a file-picker window and select a real document. Supported
file types: `.pdf`, `.xlsx`/`.xls` (Excel), `.docx` (Word), and plain text
(`.txt`, `.md`, `.csv`, ...).

## 1. Create and activate a virtual environment

```bash
cd LangChain_Basic
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

```bash
pip install -r LangChain_101/requirements.txt
```

This installs: `langchain`, `openai`, `langchain-community`, `langchain-core`,
`langchain-openai`, `streamlit`, `python-dotenv`, and the file-reading
libraries `pypdf` (PDF), `openpyxl` (Excel), `python-docx` (Word).

## 3. Fill in the .env file

Create/edit `.env` in `LangChain_101/` with your real key:

```
OPENAI_API_KEY=xxxxxxx
```

This is the only secret these scripts need — it authenticates every call to
OpenAI's chat and embeddings APIs.

## 4. Run the chatbot

```bash
cd LangChain_101
python3 chat_oi.py
```

This sends a fixed prompt ("Can you tell me something about Google?") to
`gpt-4o` and prints the answer. Edit the string inside `model.invoke(...)` to
ask something else.

## 5. Run the document embedding script

```bash
python3 embeddding_docs.py
```

You'll be asked:
```
How do you want to provide your document(s)?
  [1] Type/paste text
  [2] Load from a file - opens a window to click/navigate/select
```
- Choose `1` to type or paste text directly (type `END` on its own line when
  done).
- Choose `2` to pick a file from a native file-selector window. Works with
  `.pdf`, `.xlsx`, `.docx`, `.txt`, `.md`, `.csv`.

It prints how many documents were embedded and the length of each vector
(150, matching the `dimensions` set in the script).

## 6. Run the query embedding script

```bash
python3 embedding_query.py
```

Same `[1]`/`[2]` choice as above, but for a single piece of query text
(e.g. a search question) instead of a list of documents. Useful as the
second half of a search system: embed your documents once with step 5,
embed a question with this script, then compare the vectors (e.g. cosine
similarity) to find the closest match.

## Evolution from LangChain_100 (added later)

LangChain_100 hardcodes everything (fixed documents, fixed query, single
question/answer). These 4 additions below show the next step: making the
scripts actually *use* the embeddings they produce, and remember
conversations. New file: `embedding_utils.py`, shared by all the scripts
above and below (one copy of "read a file" / "ask the user for text"
instead of copy-pasted in every script).

**Important fix:** `embeddding_docs.py` used to embed with a *different*
model/size (`text-embedding-3-large`, 50 dims) than `embedding_query.py`
(`text-embedding-3-small`, 150 dims). You can't compare vectors from two
different models — so it was changed to match `embedding_query.py` exactly,
otherwise similarity search below would give meaningless scores.

### 1. `similarity_search.py` — find the closest document to a question

```bash
python3 embeddding_docs.py   # run first - saves doc_embeddings.json
python3 similarity_search.py # then compare a query against those docs
```

Loads the saved document vectors, embeds your query, and ranks every
document by **cosine similarity** (1.0 = same meaning, 0 = unrelated,
negative = opposite). Prints the documents best-match first.

### 2. Persisted embeddings — `doc_embeddings.json`

`embeddding_docs.py` now saves `{text, embedding}` for every document to
`doc_embeddings.json` next to it (via `save_embeddings()` /
`load_embeddings()` in `embedding_utils.py`), so you don't have to
re-embed (and re-pay for) the same documents every time you want to search
them. This file is just local output, not a secret.

### 3. `chat_memory.py` — chatbot with conversation memory

```bash
python3 chat_memory.py
```

Unlike `chat_oi.py` (one fixed question, no memory), this loops with
`input()` and keeps a `chat_history` list of `SystemMessage` /
`HumanMessage` / `AIMessage`, sending the whole history back each turn so
the model remembers earlier parts of the conversation. Type `exit` to stop.

### 4. `rag_chat.py` — minimal RAG (Retrieval-Augmented Generation)

```bash
python3 rag_chat.py
```

Ties it all together: embeds your question, finds the single closest saved
document (same idea as `similarity_search.py`), then feeds that document's
text to the chat model as context so it answers **using that document**
instead of just its general knowledge. Smaller-scale version of the same
idea as the `LangChainPDFExtract` project (PDFs -> OpenAI -> SQL Server).

## File size limit + chunking (added after hitting a 602 MB CSV)

Picking a huge file (e.g. a multi-million-row CSV) in option `[2]` used to
hang, because the whole file gets read into memory as one string and then
sent to OpenAI as one oversized embedding request. Two fixes:

- **2 MB file size cap** in `embedding_utils.py` (`MAX_FILE_BYTES`). Pick a
  file bigger than that and you get a clear message instead of a hang/crash,
  telling you to use a smaller file or paste a snippet with option `[1]`.
  A multi-million-row dataset isn't a good fit for this kind of per-file
  embedding anyway - that's hundreds of thousands of paid API calls.
- **Chunking** (`chunk_text()`): text is split into ~1000-character pieces
  with a 100-character overlap (so an idea isn't lost right at a chunk
  boundary) before being embedded. This matters for OpenAI's embedding
  models, which reject text over ~8,191 tokens (~6,000 words) in one call -
  a multi-page PDF/Word document could already be that long.

## Notes / gotchas

- Always run these with `python3`, not `py` (`py` is a Windows-only command
  and does not exist on macOS).
- Run from a real terminal, not an IDE "Run" button that doesn't support
  typing back — these scripts use `input()` and need an interactive terminal.
- `.env` should never be committed to git; keep real keys out of source
  control.
- If your editor prompts "save changes?" after I've updated a file, choose
  **Don't Save** — that keeps the version already written to disk instead of
  overwriting it with the editor's old in-memory copy.