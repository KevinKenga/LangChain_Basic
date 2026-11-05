
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv(override=True)
import os

api_key = os.getenv("OPENAI_API_KEY")

# define the model
model = ChatOpenAI(
    model ="gpt-4o-mini",
    max_tokens = 500, # do want any limit : set it to None or 500 
    openai_api_key = api_key,
    streaming = True
)

for result in model.stream("Tell me something about Nvidia Corporation"):
    print(result.content, end="", flush=True)  # print the content of the response