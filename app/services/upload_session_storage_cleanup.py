"""
Temp storage cleanup for upload agent sessions.

Analyze stores PDFs under case_id ``temp_{session_id}`` (see upload_agent analyze/confirm).
Deleting an upload session must remove that prefix on both S3 and local storage via
``storage_service.delete_case_files`` to avoid orphan objects.
"""

from __future__ import annotations

import logging
from typing import FrozenSet

from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

# Must stay in sync with ConversationState in upload_agent_service (pre-case chat only).
_RESUMABLE_STATES: FrozenSet[str] = frozenset(
    {
        "greeting",
        "waiting_for_files",
        "confirm_analysis",
        "collecting_data",
        "review_summary",
    }
)


def temp_case_id_for_session(session_id: str) -> str:
    """Virtual case id used for temp uploads during analyze (must match upload_agent)."""
    return f"temp_{session_id}"


def is_resumable_upload_state(state: str) -> bool:
    """True if the session can be resumed in the upload UI (pre-case, conversational)."""
    return state in _RESUMABLE_STATES


def delete_temp_upload_storage(*, user_id: str, session_id: str) -> int:
    """
    Delete all objects under the temp prefix for this upload session.

    Uses the same layout as save: users/{user_id}/cases/temp_{session_id}/...

    Returns:
        Number of files reported deleted (0 if prefix missing or empty).

    Raises:
        Propagates storage client errors after logging (caller may choose to swallow).
    """
    case_id = temp_case_id_for_session(session_id)
    deleted = storage_service.delete_case_files(case_id, user_id=user_id)
    logger.info(
        "Deleted %s temp storage objects for upload session %s (user %s)",
        deleted,
        session_id,
        user_id,
    )
    return deleted
