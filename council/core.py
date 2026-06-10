import os
from dotenv import load_dotenv
from pprint import pprint
from ollama import Client
from council.Agent import Agent


def call_llm(idea: str, agent: Agent) -> str:

    load_dotenv()
    OLLAMA_API_KEY = os.getenv('OLLAMA_API_KEY')

    client = Client(
        host='https://ollama.com',
        headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
    )

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
    for part in client.chat('minimax-m3:cloud', messages=messages, stream=True):
        message = part.message.content or ""

        # print(message, end='', flush=True)
        response += message

    return response
