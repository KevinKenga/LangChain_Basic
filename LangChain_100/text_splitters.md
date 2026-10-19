
## The Pipeline Order (First, the Mental Model)

```
Raw File (PDF/Word/HTML)
       ↓
   Document Loader/Parser        ← creates Document objects
       ↓
   Document Objects              ← raw, unsplit text with metadata
       ↓
   Text Splitter                 ← chunks Document objects into smaller pieces
       ↓
   Chunks (also Document objects)← now ready for embedding
       ↓
   Embedding Model
       ↓
   Vector DB
```

Yes — text splitters come **after** document objects are created.

---

## What is a Document Object?

A Document Loader/Parser just **reads the file and creates Document objects.** That's its only job.

A Document object is just a simple wrapper with two things:

python

```python
Document(
    page_content = "The full raw text of the page or file...",
    metadata     = {
        "source": "annual_report.pdf",
        "page": 4,
        "author": "John Doe",
        "created_at": "2024-01-15"
    }
)
```

That's it. No chunking, no embedding, no intelligence. Just text + metadata.

---

## How does a Document Object decide on size?

**It doesn't.** This is a key insight.

The Document Loader just mirrors the **natural structure of the source file.** It has no opinion on size whatsoever.

| Source File        | What Loader Does              | Resulting Document Size       |
| ------------------ | ----------------------------- | ----------------------------- |
| PDF (10 pages)     | 1 Document per page           | Whatever fits on one page     |
| Word Doc           | 1 Document for the whole file | Entire document as one string |
| HTML page          | 1 Document for the whole page | Full HTML stripped to text    |
| CSV                | 1 Document per row            | One row of data               |
| Notion page        | 1 Document per page           | Full page content             |
| YouTube transcript | 1 Document total              | Full transcript               |

So a 50-page PDF → 50 Document objects, each containing one page's raw text. A single Word doc → 1 Document object with everything. **The loader just reflects the file's natural boundaries.**

This is exactly why text splitters exist — because raw Document objects are almost always either too large or inconsistently sized for embedding.

---

## What is a Text Splitter?

A Text Splitter takes a Document object and **breaks it into smaller, consistently-sized chunk Documents** — each chunk is itself a new Document object with the same metadata inherited.

python

```python
# Before splitting — 1 large Document
Document(page_content="3000 words of raw text...", metadata={"source": "report.pdf"})

# After splitting — many smaller Documents
Document(page_content="first 400 tokens...",  metadata={"source": "report.pdf"})
Document(page_content="next 400 tokens...",   metadata={"source": "report.pdf"})
Document(page_content="next 400 tokens...",   metadata={"source": "report.pdf"})
# ...and so on
```

Metadata is **automatically carried forward** to every chunk — so you always know which source file a chunk came from.

## Types of Text Splitters

These go from dumb to smart:

**1. CharacterTextSplitter — dumbest, splits on character count**

```python
splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
```

Just counts characters. Doesn't care about sentences, words, meaning. Can split mid-sentence.

---

**2. RecursiveCharacterTextSplitter — the default workhorse**

python

```python
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
```

Tries to split on `\n\n` first, then `\n`, then `.`, then , then characters. Respects natural text boundaries as much as possible. **This is what most RAG systems use.**

---

**3. TokenTextSplitter — splits on actual model tokens**

python

```python
splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=64)
```

Uses the actual tokenizer (tiktoken for OpenAI, etc.) to count tokens, not characters. More accurate because embedding models have **token limits, not character limits.** 512 characters ≠ 512 tokens.

---

**4. MarkdownHeaderTextSplitter — structure-aware** Splits on `#`, `##`, `###` headers. Keeps semantically related sections together. Great for documentation.

---

**5. SemanticChunker — smartest, most expensive**

python

```python
splitter = SemanticChunker(embeddings=embedding_model)
```

Actually embeds sentences, measures cosine similarity between adjacent sentences, and splits where meaning **changes significantly.** No fixed size — chunks are determined by semantic boundaries.

The trade-off: requires embedding calls during indexing, so it's slower and costs more. But chunk quality is significantly better.

---

## The Overlap Parameter — Why It Exists

Every splitter has a `chunk_overlap` parameter. This is critical and often overlooked.

```
chunk_size=500, chunk_overlap=50

Chunk 1: chars [0   → 500] : Document object
Chunk 2: chars [450 → 950]   ← repeats last 50 chars of Chunk 1
Chunk 3: chars[900 → 1400]  ← repeats last 50 chars of Chunk 2
```

Without overlap, if a key sentence lands exactly on a chunk boundary, it gets cut in half — and neither chunk has the full context. Overlap ensures **no critical information is orphaned at a boundary.**

Typical overlap is 10-15% of chunk size.
