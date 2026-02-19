"""Event validation utilities for timeline"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def validate_event_consistency(events: List[Dict]) -> List[Dict]:
    """
    Validate event consistency and remove invalid events
    
    Args:
        events: List of event dictionaries
        
    Returns:
        Filtered list of valid events
    """
    valid_events = []
    
    for event in events:
        if not isinstance(event, dict):
            logger.warning(f"Skipping non-dict event: {type(event)}")
            continue
        
        # Must have event_type and description
        if not event.get("event_type") or not event.get("description"):
            logger.debug(f"Skipping event missing event_type or description: {event.get('id', 'unknown')}")
            continue
        
        # Must have date or sort_date
        if not event.get("date") and not event.get("sort_date"):
            logger.debug(f"Skipping event missing date: {event.get('id', 'unknown')}")
            continue
        
        # Must have source information
        if not event.get("source_file") and not event.get("details", {}).get("source_file"):
            logger.debug(f"Skipping event missing source_file: {event.get('id', 'unknown')}")
            continue
        
        valid_events.append(event)
    
    return valid_events


def filter_events_without_sources(events: List[Dict]) -> List[Dict]:
    """
    Filter out events that don't have source file information
    (Critical for audit requirements)
    
    Args:
        events: List of event dictionaries
        
    Returns:
        Filtered list of events with source information
    """
    filtered = []
    
    for event in events:
        # Check for source_file in event or details
        has_source = (
            event.get("source_file") or
            event.get("details", {}).get("source_file") or
            event.get("source_page") is not None or
            event.get("details", {}).get("source_page") is not None
        )
        
        if has_source:
            filtered.append(event)
        else:
            logger.warning(f"Filtering out event without source: {event.get('id', 'unknown')} - {event.get('description', '')[:50]}")
    
    return filtered


def validate_event_descriptions(events: List[Dict]) -> List[Dict]:
    """
    Validate and clean event descriptions
    
    Args:
        events: List of event dictionaries
        
    Returns:
        List of events with validated descriptions
    """
    for event in events:
        description = event.get("description", "")
        if not description or not isinstance(description, str):
            # Generate a basic description if missing
            event_type = event.get("event_type", "event")
            event["description"] = f"{event_type.title()} event"
        else:
            # Clean up description
            event["description"] = description.strip()
            
            # Remove excessive whitespace
            event["description"] = " ".join(event["description"].split())
            
            # Ensure it's not too long (truncate if needed)
            from app.core.constants import MAX_DESCRIPTION_LENGTH
            if len(event["description"]) > MAX_DESCRIPTION_LENGTH:
                event["description"] = event["description"][:MAX_DESCRIPTION_LENGTH-3] + "..."
    
    return events


def deduplicate_events(events: List[Dict]) -> List[Dict]:
    """
    Remove duplicate events based on id, date, and description
    
    Args:
        events: List of event dictionaries
        
    Returns:
        List of unique events
    """
    seen = set()
    unique_events = []
    
    for event in events:
        # Create a unique key from id, date, and description
        event_id = event.get("id", "")
        event_date = event.get("date", "")
        description = event.get("description", "")[:100]  # First 100 chars
        
        key = f"{event_id}|{event_date}|{description}"
        
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    return unique_events

