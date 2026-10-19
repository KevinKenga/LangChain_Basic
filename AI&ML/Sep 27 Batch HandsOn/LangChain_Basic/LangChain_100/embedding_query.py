'''
OpenAIEmbeddings()
embed_query is used when you want to embed a single query or small piece of text. 
It returns a vector representation of the input text, which can be used for various tasks such as semantic search, clustering, or similarity comparisons.

embed_docs are used with corpus of documents, or multiple paragraphs of text. 
It returns a list of vector representations, one for each document or paragraph in the input list. This is useful for tasks like document retrieval, topic modeling, or any application where you need to process and analyze multiple pieces of text at once.
'''
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(override=True)
import os
api_key = os.getenv("OPENAI_API_KEY")

embedding = OpenAIEmbeddings(
    model = "text-embedding-3-small",
    dimensions = 150,
    api_key = api_key
)

text = "There are three built-in styles: **default** (balanced, explains as it goes), \
        **concise** (only the code and a line or two) and **explanatory** \
        (teaches while it works, useful for people new to the code)."
        
embedding_vec = embedding.embed_query(text)
print(embedding_vec)
print(f"Length of embedding vector: {len(embedding_vec)}")