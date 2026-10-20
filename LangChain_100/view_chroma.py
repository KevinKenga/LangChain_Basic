'''
Visual viewer for the local Chroma vector store (kev_chroma_db).
Lets you browse collections, rows, IDs, documents, metadata, and embeddings.

Run with:
    streamlit run view_chroma.py
'''

import os
import pandas as pd
import streamlit as st
import chromadb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "kev_chroma_db")

st.set_page_config(page_title="Chroma DB Viewer", layout="wide")
st.title("Chroma Vector Store Viewer")
st.caption(f"DB path: {DB_DIR}")

if not os.path.isdir(DB_DIR):
    st.error(f"No Chroma DB found at {DB_DIR}. Run chroma.py first to create it.")
    st.stop()

client = chromadb.PersistentClient(path=DB_DIR)
collections = client.list_collections()

if not collections:
    st.warning("No collections found in this Chroma DB.")
    st.stop()

collection_names = [c.name for c in collections]
selected_name = st.selectbox("Collection", collection_names)
collection = client.get_collection(selected_name)

total_rows = collection.count()
st.metric("Total rows", total_rows)

max_rows = st.slider("Rows to show", min_value=5, max_value=min(total_rows, 500), value=min(20, total_rows))

data = collection.get(limit=max_rows, include=["documents", "metadatas", "embeddings"])

rows = []
for i in range(len(data["ids"])):
    embedding = data["embeddings"][i] if data.get("embeddings") is not None else None
    rows.append({
        "id": data["ids"][i],
        "document": (data["documents"][i][:200] + "...") if data["documents"][i] and len(data["documents"][i]) > 200 else data["documents"][i],
        "metadata": data["metadatas"][i],
        "embedding_dim": len(embedding) if embedding is not None else 0,
    })

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True)

st.subheader("Inspect a single row")
chosen_id = st.selectbox("Row ID", [r["id"] for r in rows])
chosen = next(r for r in rows if r["id"] == chosen_id)
st.json(chosen["metadata"])
st.write("Document text:")
full_doc = collection.get(ids=[chosen_id], include=["documents"])["documents"][0]
st.text(full_doc)
