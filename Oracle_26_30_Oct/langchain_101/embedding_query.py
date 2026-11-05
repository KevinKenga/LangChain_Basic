from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(override=True)
import os
api_key = os.getenv("OPENAI_API_KEY")

# define the embeddings model
embeddings = OpenAIEmbeddings(
    model ="text-embedding-3-small", # text ---> 1536 D
    dimensions = 150,
    openai_api_key = api_key
)

# text 
text = "Oracle Corporation is an American multinational computer technology corporation headquartered in Austin, Texas. \
    The company sells database software and technology, cloud engineered systems, and enterprise software products—particularly \
     its own brands of database management systems. "
     
embedding_vector = embeddings.embed_query(text)
print(embedding_vector)  # print the embedding vector
print(f"Length of embedding vector: {len(embedding_vector)}")  # print the length of the embedding vector