'''
chroma db : local vector database
it creates local vector store and stores the embeddings 

id , textual chunks, embeddings, metadata
'''

import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from dotenv import load_dotenv
load_dotenv(override=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(BASE_DIR, "gpt-1paper.pdf")
DB_DIR = os.path.join(BASE_DIR, "kev_chroma_db")
COLLECTION = "gpt-1paper"

# create the document loader object
docs = PyPDFLoader(PDF_PATH).load()
print(f"Number of documents loaded: {len(docs)} from the {PDF_PATH}")

# create the text splitter object
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=140
)

chunks = text_splitter.split_documents(docs)
print(f"Number of chunks created: {len(chunks)}")

# for each chunk , we need to give an id
# id : chunk_id

ids = [f"chunk_{i}" for i in range(len(chunks))]

# create the embeddings object
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# define the vector store

vector_store = Chroma(
    collection_name = COLLECTION,
    embedding_function = embeddings,
    persist_directory = DB_DIR
)

# send each chunk to the vector store
vector_store.add_documents(chunks, ids=ids)
print(f"Chunks stored in Chroma DB : ", len(vector_store.get()["ids"]))

# read 3 chunks from the vector store
stored = vector_store.get(limit=3,include =["metadatas","documents","embeddings"])


for i in range(len(stored["ids"])):
    vector = stored["embeddings"][i]
    print(f"Chunk {i} :")
    print("ID : ", stored["ids"][i])
    print("Text : ", stored["documents"][i])
    print("Metadata : ", stored["metadatas"][i])
    print("Embedding length : ", len(vector))
    print("Vectors: ", vector[:10])  # print first 10 elements of the vector
    print("="*60)