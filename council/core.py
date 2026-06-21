"""LLM core functions for IdeaCouncil."""

import json
import os
import re
from typing import Optional

import httpx
from dotenv import load_dotenv


load_dotenv()

# Default model - can be overridden via environment variable
DEFAULT_MODEL = os.getenv("LLM_MODEL", "qwen2.5:14b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def call_llm(system: str, user: str, model: Optional[str] = None) -> str:
    """
    Base LLM call - sends a prompt to Ollama and returns the response.

    Args:
        system: System prompt
        user: User prompt
        model: Model name (defaults to DEFAULT_MODEL)

    Returns:
        The LLM's response as a string
    """
    load_dotenv()

    model = model or DEFAULT_MODEL

    # Check if using remote Ollama or local
    if OLLAMA_HOST.startswith("http"):
        api_key = os.getenv("OLLAMA_API_KEY", "")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        client = httpx.Client(timeout=300.0)
        response = client.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
            headers=headers,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    # Local Ollama using ollama library
    from ollama import Client

    client = Client(host=OLLAMA_HOST)
    resp = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp["message"]["content"]


def call_llm_json(system: str, user: str, model: Optional[str] = None) -> dict:
    """
    LLM call that parses JSON from the response.

    Tries to parse JSON from the response. If that fails, strips markdown
    code blocks and tries again. If it fails twice, raises an exception.

    Args:
        system: System prompt
        user: User prompt
        model: Model name (defaults to DEFAULT_MODEL)

    Returns:
        Parsed JSON as a dictionary

    Raises:
        ValueError: If JSON parsing fails after both attempts
    """
    response = call_llm(system, user, model)

    # Try 1: Direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try 2: Strip markdown code blocks
    stripped = response.strip()
    if stripped.startswith("```"):
        # Find the JSON block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # Try 3: Find raw JSON without code blocks
    start = response.find("{")
    end = response.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(response[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Failed to parse JSON from LLM response:\n{response[:500]}")


def format_lawyer_r2_prompt(dimension: str, idea: "Idea", transcript: str) -> str:
    """
    Format a Round 2 lawyer prompt with the idea and transcript.
    """
    from council.prompts import LAWYER_PROMPTS_R2

    base_prompt = LAWYER_PROMPTS_R2[dimension]

    # Replace placeholders
    prompt = base_prompt.replace("{idea}", f"Title: {idea.title}\n{idea.one_liner}")
    prompt = prompt.replace("{transcript}", transcript)

    return prompt


# Import Idea for type hints (at end to avoid circular imports)
from council.models import Idea  # noqa: E402
