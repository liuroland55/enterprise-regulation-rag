"""
JSON Parser Module for Local Model Compatibility

This module provides robust JSON parsing utilities specifically designed to handle
the output of local LLMs (Ollama models), which often include:
- Markdown code block markers (```json, ```)
- Trailing commas
- Comments
- Extra text before/after JSON
- Malformed JSON due to token limits
"""

import json
import re
from typing import Any, Dict, Optional


def parse_json_safely(text: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    Safely parse JSON from LLM output with multiple fallback strategies.
    
    This function is essential for local models that may not produce perfectly
    formatted JSON. It applies a series of cleaning and repair strategies.
    
    Args:
        text: Raw text from LLM response
        max_retries: Maximum number of parsing attempts with different strategies
        
    Returns:
        Dict[str, Any]: Parsed JSON object
        
    Raises:
        ValueError: If all parsing strategies fail
        
    Example:
        >>> text = '''Here's the answer:
        ... ```json
        ... {"answer": "Paris", "confidence": 0.95}
        ... ```
        ... '''
        >>> result = parse_json_safely(text)
        >>> result["answer"]
        'Paris'
    """
    # Strategy 1: Direct parsing (for well-formed JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract JSON from markdown code blocks
    json_content = extract_json_from_markdown(text)
    if json_content:
        try:
            return json.loads(json_content)
        except json.JSONDecodeError:
            pass
    
    # Strategy 3: Clean and repair common issues
    cleaned_text = clean_json_text(text)
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass
    
    # Strategy 4: Extract and clean from markdown
    if json_content:
        cleaned_json = clean_json_text(json_content)
        try:
            return json.loads(cleaned_json)
        except json.JSONDecodeError:
            pass
    
    # If all strategies fail, raise detailed error
    raise ValueError(
        f"Failed to parse JSON after {max_retries} strategies. "
        f"Last attempted text:\n{cleaned_text[:500]}..."
    )


def extract_json_from_markdown(text: str) -> Optional[str]:
    """
    Extract JSON content from markdown code blocks.
    
    Handles patterns like:
    ```json
    {...}
    ```
    
    Or even without the json specifier:
    ```
    {...}
    ```
    
    Args:
        text: Raw text that may contain markdown code blocks
        
    Returns:
        Optional[str]: Extracted JSON content, or None if not found
    """
    # Pattern 1: ```json ... ```
    pattern1 = r'```json\s*([\s\S]*?)\s*```'
    match = re.search(pattern1, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: ``` ... ``` (no language specified)
    pattern2 = r'```\s*([\s\S]*?)\s*```'
    match = re.search(pattern2, text)
    if match:
        content = match.group(1).strip()
        # Verify it looks like JSON (starts with { or [)
        if content.startswith(('{', '[')):
            return content
    
    return None


def clean_json_text(text: str) -> str:
    """
    Clean and repair common JSON formatting issues from LLM output.
    
    Fixes:
    - Trailing commas (e.g., {"a": 1,} -> {"a": 1})
    - Comments (e.g., /* comment */ or // comment)
    - Control characters
    - Extra text before/after JSON
    
    Args:
        text: Raw JSON-like text
        
    Returns:
        str: Cleaned JSON text ready for parsing
    """
    # Remove comments (both // and /* */ style)
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    
    # Remove trailing commas (e.g., "key": value, -> "key": value)
    # This regex handles trailing commas before closing brackets/braces
    text = re.sub(r',\s*([}\]])', r'\1', text)
    
    # Remove control characters except newline and tab
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Strip whitespace
    text = text.strip()
    
    # Try to find the first { and last } to extract JSON object
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    
    return text


def validate_json_structure(data: Dict[str, Any], required_keys: list) -> bool:
    """
    Validate that JSON response contains required keys.
    
    Args:
        data: Parsed JSON dictionary
        required_keys: List of required key names
        
    Returns:
        bool: True if all required keys are present
        
    Raises:
        ValueError: If required keys are missing, with detailed message
    """
    missing_keys = [key for key in required_keys if key not in data]
    
    if missing_keys:
        raise ValueError(
            f"JSON response missing required keys: {missing_keys}. "
            f"Available keys: {list(data.keys())}"
        )
    
    return True


# Convenience exports
__all__ = ["parse_json_safely", "extract_json_from_markdown", "clean_json_text", "validate_json_structure"]