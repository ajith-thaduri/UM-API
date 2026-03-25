"""Unit tests for upload session temp storage cleanup helpers."""

import pytest
from unittest.mock import patch

from app.services.upload_agent_service import ConversationState
from app.services.upload_session_storage_cleanup import (
    delete_temp_upload_storage,
    is_resumable_upload_state,
    temp_case_id_for_session,
)


def test_temp_case_id_for_session():
    assert temp_case_id_for_session("abc-123") == "temp_abc-123"


@pytest.mark.parametrize(
    "state,expected",
    [
        (ConversationState.GREETING.value, True),
        (ConversationState.WAITING_FOR_FILES.value, True),
        (ConversationState.CONFIRM_ANALYSIS.value, True),
        (ConversationState.COLLECTING_DATA.value, True),
        (ConversationState.REVIEW_SUMMARY.value, True),
        (ConversationState.PROCESSING.value, False),
        (ConversationState.COMPLETE.value, False),
        (ConversationState.ERROR.value, False),
        ("analyzing_files", False),
        ("unknown_state", False),
    ],
)
def test_is_resumable_upload_state_matrix(state: str, expected: bool):
    assert is_resumable_upload_state(state) is expected


@patch("app.services.upload_session_storage_cleanup.storage_service")
def test_delete_temp_upload_storage_delegates(mock_storage):
    mock_storage.delete_case_files.return_value = 5
    n = delete_temp_upload_storage(user_id="user-1", session_id="sess-1")
    assert n == 5
    mock_storage.delete_case_files.assert_called_once_with("temp_sess-1", user_id="user-1")
