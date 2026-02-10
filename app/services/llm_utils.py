"""Utility functions for LLM responses"""

import json
import re
import logging

logger = logging.getLogger(__name__)


# Centralized extraction rules to be appended to LLM prompts for deduplication
EXTRACTION_RULES = """

EXTRACTION RULES:
1. Return ONLY valid JSON. Do not include markdown code fences.
2. Extract each unique clinical entity ONCE per date.
3. If the same item appears multiple times, keep the entry with the most complete information (include source_page).
4. Prefer quality over quantity - complete entries over duplicate partial entries.
5. Always include source_file and source_page when available."""


def extract_json_from_response(response: str) -> dict:
    """
    Extract JSON from LLM response, handling markdown code blocks and extra text.
    
    Claude sometimes wraps JSON in markdown code blocks like:
    ```json
    {...}
    ```
    
    Args:
        response: Raw response string from LLM
        
    Returns:
        Parsed JSON dictionary
        
    Raises:
        ValueError: If no valid JSON can be extracted
        json.JSONDecodeError: If JSON is malformed
    """
    if not response or not response.strip():
        raise ValueError("Empty response from LLM")
    
    original_response = response
    response = response.strip()
    
    # Step 1: Strip markdown code fences first if present
    # This handles both ```json and ``` variants
    if response.startswith('```'):
        # Use regex to strip the opening fence and any language identifier
        # This is robust to missing newlines or truncated starts
        response = re.sub(r'^```(?:json|markdown)?\s*', '', response, flags=re.IGNORECASE)
        
        # Check if it ends with closing fence and strip it
        if response.endswith('```'):
            response = response[:-3]
            
        response = response.strip()
    
    # Try direct JSON parsing (most common case after stripping fences)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from remaining markdown code blocks 
    # (in case there are nested or multiple code blocks)
    json_block_pattern = r'```(?:json)?\s*(\{[\s\S]*?\})\s*```'
    match = re.search(json_block_pattern, response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON from code block: {e}. JSON: {match.group(1)[:200]}")
            pass
    
    # Try to find JSON object boundaries (find first { and last })
    first_brace = response.find('{')
    last_brace = response.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = response[first_brace:last_brace + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON array boundaries (find first [ and last ])
    first_bracket = response.find('[')
    last_bracket = response.rfind(']')
    
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        json_str = response[first_bracket:last_bracket + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # If all else fails, log the response and raise an error
    logger.error(f"Could not extract valid JSON from response. First 500 chars: {original_response[:500]}")
    raise ValueError(f"Could not extract valid JSON from response: {original_response[:200]}")

