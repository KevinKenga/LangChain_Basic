'''
Document loader :
1. helps us work with the document types: pdf, docx, txt, csv, etc.
2. creates document objects aka chunks

'''
from langchain_community.document_loaders import PyPDFLoader

import os

# load the PDF that lives in the same folder as this script
pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpt-1paper.pdf")
loader = PyPDFLoader(pdf_path)

# create the document object
docs = loader.load()

print(f"Number of documents loaded: {len(docs)}")
print("="*50) # ======================
print(docs)
print("="*50)
print(f"First document object content: {docs[0].page_content}")
# the above is the page content on first page of the pdf