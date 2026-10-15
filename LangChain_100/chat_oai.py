'''
chat model : 
I am going to chat with gpt models using langchain as an inteface
using my python client (here the py client is vs code)
library : ChatOpenAI

libraries : syntax : 2 

import library name as alias
example : import pandas as pd

from library_name import module
from langchain_openai import ChatOpenAI
'''
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv
load_dotenv(override=True)
import os

api_key = os.getenv("OPENAI_API_KEY")

model = ChatOpenAI(
    model="gpt-4o",
    max_tokens = 500 , # set max_tokens = None
    openai_api_key = api_key
)

# .invoke means to apply
# apply the model on the prompt
result = model.invoke("Can you tell me something about Google?")
# print(result)
# output here is made up of 2 things : content and metadata
# metadata is information about the data
print(result.content)