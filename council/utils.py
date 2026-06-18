import json, re

def write_to_file(filename, content):
    with open(filename, 'w') as f:
        f.write(content)

def append_to_file(filename, content):
    with open(filename, 'a') as f:
        f.write(content)

def parse_critique_response(response_text: str):
    """
    Extracts JSON from an LLM response robustly.
    Returns: (dict_data, text_summary)
    """
    data = None
    json_str = None
    text_to_remove = ""

    # Strategy 1: Look for standard ```json ... ``` or ``` ... ``` blocks
    block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    match = re.search(block_pattern, response_text, re.DOTALL | re.IGNORECASE)

    if match:
        json_str = match.group(1)
        text_to_remove = match.group(0)
    else:
        # Strategy 2: Fallback if LLM forgot code blocks entirely.
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx + 1]
            text_to_remove = json_str

    if not json_str:
        print("Warning: Could not locate any JSON-like structure.")
        # Make sure to ALWAYS return a tuple so unpacking doesn't crash
        return None, response_text.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Warning: Found JSON-like structure but failed to parse: {e}")
        return None, response_text.strip()

    summary = response_text.replace(text_to_remove, '').strip()
    return data, summary


def parse_json_response(response_text: str) -> dict:
    """
    Parse JSON from an LLM response. Simpler version for when you just need the dict.

    Args:
        response_text: Raw LLM response

    Returns:
        Parsed JSON dict

    Raises:
        ValueError: If JSON cannot be parsed
    """
    data = None
    json_str = None

    # Strategy 1: Look for ```json ... ``` blocks
    block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    match = re.search(block_pattern, response_text, re.DOTALL | re.IGNORECASE)

    if match:
        json_str = match.group(1)
    else:
        # Strategy 2: Find raw JSON
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx + 1]

    if not json_str:
        raise ValueError(f"Could not locate JSON in response: {response_text[:200]}")

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}\nContent: {json_str[:200]}")
