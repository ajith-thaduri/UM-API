"""Utility functions for LLM responses"""

import json
import re
import logging

logger = logging.getLogger(__name__)


# Centralized extraction rules to be appended to LLM prompts for deduplication
EXTRACTION_RULES = """

EXTRACTION RULES:
1. Return ONLY valid JSON. Do not include markdown code fences.
2. GROUNDING: Extract ONLY information explicitly stated in the provided context.
3. Extract each unique clinical entity ONCE per date.
4. If the same item appears multiple times, keep the entry with the most complete information (include source_page).
5. Prefer quality over quantity - accurate, grounded entries only.
6. Always include source_file and source_page when available.
7. CRITICAL: If information is not in the context, DO NOT fabricate or infer - omit the field or return null.
8. When dates are given as ranges, report the range - do not create specific dates.
9. When values are given as ranges (e.g., "glucose 180-280"), report the range - do not invent specific values."""


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

    # Last resort: the LLM may have returned a truncated JSON object (cut off mid-stream).
    # Attempt to auto-close the truncated string so the parser can at least recover the
    # fields that were fully written before the cutoff.
    if first_brace != -1:
        truncated = response[first_brace:]
        # Count unmatched braces/brackets/quotes to decide what to append
        closers: list[str] = []
        in_string = False
        escape_next = False
        for ch in truncated:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                closers.append('}')
            elif ch == '[':
                closers.append(']')
            elif ch in (')', '}', ']') and closers:
                closers.pop()

        # If we were mid-string, close it first
        tail = '"' if in_string else ''
        tail += ''.join(reversed(closers))

        if tail:
            try:
                recovered = json.loads(truncated + tail)
                logger.warning(
                    "Recovered partial JSON from truncated LLM response (appended %r). "
                    "First 200 chars of original: %s",
                    tail, original_response[:200],
                )
                return recovered
            except json.JSONDecodeError:
                pass

    # Extra recovery: LLM sometimes truncates as {"final{" or {"key": { (no content).
    # Close the open string (key), add : null, then close braces. Try 1 and 2 closing braces
    # because a "{" inside the key string shouldn't count as an open brace.
    if first_brace != -1:
        truncated_trim = response[first_brace:].rstrip()
        open_brackets = max(0, truncated_trim.count("[") - truncated_trim.count("]"))
        for n_close in range(1, 4):
            try:
                candidate = truncated_trim + '": null' + "]" * open_brackets + "}" * n_close
                recovered = json.loads(candidate)
                logger.warning(
                    "Recovered truncated JSON (appended ': null' + %d closers). First 200 chars: %s",
                    n_close, original_response[:200],
                )
                return recovered
            except json.JSONDecodeError:
                continue

    logger.error(f"Could not extract valid JSON from response. First 500 chars: {original_response[:500]}")
    raise ValueError(f"Could not extract valid JSON from response: {original_response[:200]}")

