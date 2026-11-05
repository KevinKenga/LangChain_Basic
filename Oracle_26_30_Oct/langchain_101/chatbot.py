'''
3 messages
System Message : System instructions
AI Message : LLM generated output 
Human Message : Prompt/Query that user gives
'''

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
load_dotenv(override=True)
import os

model = ChatOpenAI(model="gpt-4o-mini", max_tokens=500, openai_api_key=os.getenv("OPENAI_API_KEY"))

# chat history : all the messages exchanged between user and AI

chat_history = [
    SystemMessage(
        content ="You are a helpful assistant. You answer the questions on the context provided.\
            You do not make up any information"
    )
]

while True:
    user_input = input("User: ")
    chat_history.append(HumanMessage(content=user_input))
    # after this my chat history will contain the system message, user message 
    if user_input == "exit":
        break
    
    # then on the chat history , llm will be applied
    # and llm generated output will be appended to the chat history as AI message
    response = model.invoke(chat_history)
    chat_history.append(AIMessage(content=response.content))
    
    # now chat history will contain system message, user message, AI message
    print(f"AI : {response.content}")  # print the content of the response
    
print("Ending the chat session......\n")
print("Chat history:", chat_history)