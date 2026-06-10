from pprint import pprint
from ollama import Client
from council.Agent import Agent

def call_llm(idea: str, agent: Agent) -> str:
    # ollama client
    client = Client()

    messages = [
      {
        'role': 'system',
        'content': agent.system_prompt,
      },
      {
        'role': 'user',
        'content': idea,
      },
    ]

    response = ""
    for part in client.chat('llama3.2:1b', messages=messages, stream=True):
        message = part.message.content or ""

        # print(message, end='', flush=True)
        response += message

    return response
