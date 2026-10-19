'''
text splitting : Chunking 
Doc objects --> Text Splitter --> Chunks
'''
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

import os

# load the PDF that lives in the same folder as this script
pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpt-1paper.pdf")
loader = PyPDFLoader(pdf_path)

# create the document object
docs = loader.load()

print(f"Number of documents loaded: {len(docs)}")
print("="*50) # ======================
print(f"First document object content: {docs[1].page_content}")
print("Starting the chunking process...\n")

# create the text splitter object
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=140
)

# create the chunks
chunks = text_splitter.split_documents(docs)

print(f"Number of chunks created: {len(chunks)}")
print("="*50) # ======================
print(f"First chunk content: {chunks[0].page_content}")
print("="*50) # ======================
print(f"Second chunk content: {chunks[1].page_content}")