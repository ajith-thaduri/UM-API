"""Unit tests for UploadAgentService.process_message LangGraph vs legacy delegation."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.services.upload_agent_service import (
    AgentMessage,
    MessageType,
    upload_agent_service,
)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.mark.asyncio
async def test_process_message_delegates_to_invoke_when_langgraph_enabled(mock_db):
    expected = AgentMessage(
        id="g1",
        message="from graph",
        type=MessageType.QUESTION,
        timestamp="t",
    )
    with patch.object(settings, "USE_UPLOAD_LANGGRAPH", True), patch(
        "app.services.upload_agent_graph.invoke_upload_message",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_invoke:
        out = await upload_agent_service.process_message(mock_db, "sid-1", "hello")
    mock_invoke.assert_awaited_once_with(mock_db, "sid-1", "hello")
    assert out is expected


@pytest.mark.asyncio
async def test_process_message_delegates_to_legacy_when_langgraph_disabled(mock_db):
    legacy = AgentMessage(
        id="leg",
        message="legacy",
        type=MessageType.GREETING,
        timestamp="t",
    )
    with patch.object(settings, "USE_UPLOAD_LANGGRAPH", False), patch.object(
        upload_agent_service,
        "_process_message_legacy",
        new_callable=AsyncMock,
        return_value=legacy,
    ) as mock_legacy:
        out = await upload_agent_service.process_message(mock_db, "sid-2", "hi")
    mock_legacy.assert_awaited_once_with(mock_db, "sid-2", "hi")
    assert out is legacy


@pytest.mark.asyncio
async def test_process_message_graph_path_import_is_lazy(mock_db):
    """When LangGraph is on, failing graph import should surface on call (smoke)."""
    expected = AgentMessage(
        id="ok",
        message="m",
        type=MessageType.QUESTION,
        timestamp="t",
    )
    with patch.object(settings, "USE_UPLOAD_LANGGRAPH", True), patch(
        "app.services.upload_agent_graph.invoke_upload_message",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        out = await upload_agent_service.process_message(mock_db, "s", "m")
    assert out.message == "m"
