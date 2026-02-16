"""Date utility functions for timeline processing"""

import re
from datetime import datetime, timedelta
from typing import Optional


def normalize_date_format(date_str: str) -> Optional[str]:
    """
    Normalize various date formats to MM/DD/YYYY
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        Normalized date string in MM/DD/YYYY format, or None if invalid
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    date_str = date_str.strip()
    
    # Remove common prefixes
    if date_str.lower().startswith("on "):
        date_str = date_str[3:].strip()
    if date_str.lower().startswith("date: "):
        date_str = date_str[6:].strip()
    
    # Try common date formats
    formats = [
        "%m/%d/%Y",      # 01/15/2024
        "%m-%d-%Y",      # 01-15-2024
        "%Y-%m-%d",      # 2024-01-15
        "%B %d, %Y",     # January 15, 2024
        "%b %d, %Y",     # Jan 15, 2024
        "%d %B %Y",      # 15 January 2024
        "%d %b %Y",      # 15 Jan 2024
        "%B %d %Y",      # January 15 2024 (no comma)
        "%b %d %Y",      # Jan 15 2024
        "%d %B %Y",      # 15 January 2024
        "%d %b %Y",      # 15 Jan 2024
        "%m/%d/%y",      # 01/15/24
        "%Y/%m/%d",      # 2024/01/15
        "%d-%m-%Y",      # 15-01-2024 (EU)
        "%Y.%m.%d",      # 2024.01.15
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            continue
    
    # Try regex patterns for common medical date formats
    patterns = [
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', r'\1/\2/\3'),  # Already MM/DD/YYYY
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', r'\2/\3/\1'),  # YYYY-MM-DD -> MM/DD/YYYY
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', r'\1/\2/\3'),  # MM-DD-YYYY -> MM/DD/YYYY
    ]
    
    for pattern, replacement in patterns:
        match = re.match(pattern, date_str)
        if match:
            try:
                # Validate the date
                if len(match.groups()) == 3:
                    month, day, year = match.groups()
                    dt = datetime(int(year), int(month), int(day))
                    return dt.strftime("%m/%d/%Y")
            except (ValueError, TypeError):
                continue
    
    return None


def parse_date_for_sort(date_str: Optional[str]) -> datetime:
    """
    Parse date string to datetime for sorting purposes.
    Returns epoch (1970-01-01) if parsing fails.
    
    Args:
        date_str: Date string to parse
        
    Returns:
        datetime object for sorting
    """
    if not date_str:
        return datetime(1970, 1, 1)
    
    # Try normalized format first
    normalized = normalize_date_format(date_str)
    if normalized:
        try:
            return datetime.strptime(normalized, "%m/%d/%Y")
        except ValueError:
            pass
    
    # Try direct parsing
    formats = [
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Return epoch as fallback (sorts to beginning)
    return datetime(1970, 1, 1)


def get_date_from_dict(item: dict, keys: Optional[list] = None) -> Optional[str]:
    """
    Extract date from dictionary using multiple possible keys
    
    Args:
        item: Dictionary to search
        keys: List of keys to try (default: common date field names)
        
    Returns:
        Date string if found, None otherwise
    """
    if keys is None:
        keys = ["date", "event_date", "occurrence_date", "start_date", "created_date", "timestamp"]
    
    for key in keys:
        if key in item and item[key]:
            value = item[key]
            if isinstance(value, str):
                return value
            elif isinstance(value, datetime):
                return value.strftime("%m/%d/%Y")
            elif hasattr(value, 'isoformat'):
                # Handle date objects
                try:
                    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                    return dt.strftime("%m/%d/%Y")
                except (ValueError, AttributeError):
                    pass
    
    return None


