'''
OpenAIEmbeddings()

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