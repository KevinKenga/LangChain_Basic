'''
chroma db : store vectors locally
it creates the vector store in the current working directory
sqlite db : store vectors in a sqlite database

each vector store : 
1. id 
2. Textual chunk / candidate 
3. embeddings of the chunks
4. Metadata : source of the chunk, page number, etc

'''

import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
load_dotenv(override=True)

PDF_PATH = "/Volumes/Work/Oracle_26_30Oct/langchain_101/gpt-1paper.pdf"
DB_DIR = "./first_chroma_db"  # directory to store the vector store
COLLECTION = "test_collection"  # name of the collection in the vector store

# create a loader object 
loader = PyPDFLoader(PDF_PATH)
print("Loader object created successfully ......")

# create the document object
document_objects = loader.load()

# print the first document object
print("Document object created successfully ......")
print(f"Length of document objects being created : {len(document_objects)}")  # print the length of the document object
print(f"First document object : {document_objects[0].page_content}")  

print("="* 50)
print("Chunking process started ......")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = 300,
    chunk_overlap = 120
)

# apply the text splitter to the document object
chunks = text_splitter.split_documents(document_objects)
print(f"Chunks created successfully ...... Total chunks : {len(chunks)}")
print("="* 50)
print(f"First chunk : {chunks[0].page_content}")  # print the first chunk
print("="* 50)
print(f"Second chunk : {chunks[1].page_content}")  # print the second

print("="* 50)

# generate id
# chunk_1 , chunk_2
ids = [f"chunk_{i}" for i in range(len(chunks))]

embedding = OpenAIEmbeddings(model ="text-embedding-3-small", openai_api_key = os.getenv("OPENAI_API_KEY"))

# define the vector store
vector_store = Chroma(
    collection_name = COLLECTION,
    embedding_function = embedding,
    persist_directory = DB_DIR
)

# send each chunk to the vector store
vector_store.add_documents(chunks, ids = ids)
print("Chunks stored in Chroma: ", len(vector_store.get()["ids"]))  # print the number of chunks stored in the vector store


# read 3 sample chunks from the vector store
stored = vector_store.get(limit = 3, include = ["metadatas", "documents", "embeddings"])

for i in range(len(stored["ids"])):
    vector = stored["embeddings"][i]
    print(f"Chunk {i}: ")
    print(f"ID: {stored['ids'][i]}")
    print(f"Textual chunk: {stored['documents'][i]}")
    print(f"Metadata: {stored['metadatas'][i]}")
    print("Embedding vector length: ", len(vector))
    print(f"First 10 vectors per chunk: {vector[:10]}")
    print("="* 50)