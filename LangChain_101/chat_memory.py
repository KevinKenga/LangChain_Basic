"""
chat_memory.py
===============
STEP 3 of the "evolution from LangChain_100" plan.

chat_oi.py asks ONE fixed question and prints ONE answer - the model has no
idea what was asked before. This script turns that into a real back-and-forth
conversation by keeping a running list of messages (`chat_history`) and
sending the whole list back to the model every turn, so it can refer to
earlier things you said.

Message types (same ones used in LangChain_100/messages.py):
- SystemMessage: instructions for how the assistant should behave
- HumanMessage:  something you (the user) typed
- AIMessage:     something the model replied with

Type `exit` at any prompt to end the conversation.
"""
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")

model = ChatOpenAI(model="gpt-4o", api_key=api_key)

chat_history = [
    SystemMessage(content="You are a helpful assistant. Keep answers concise."),
]

if __name__ == "__main__":
    print("Chat with memory - type 'exit' to stop.\n")
    while True:
        user_input = input("You: ")
        if user_input.strip().lower() == "exit":
            break

        chat_history.append(HumanMessage(content=user_input))
        response = model.invoke(chat_history)
        chat_history.append(AIMessage(content=response.content))

        print(f"AI: {response.content}\n")

    print("Chat session ended.")
