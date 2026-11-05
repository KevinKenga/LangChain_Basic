'''
chat model : 
connect python client to gpt models
using langchain 
'''

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv(override=True)
import os

api_key = os.getenv("OPENAI_API_KEY")

# define the model
model = ChatOpenAI(
    model ="gpt-4o-mini",
    max_tokens = 500, # do want any limit : set it to None or 500 
    openai_api_key = api_key
)

# apply the model to a prompt
prompt = "Tell me something about Oracle Corporation"

# langchain : invoke means to apply
response = model.invoke(prompt)

# response means content and metadata
# print(response)
print(response.content)  # print the content of the response