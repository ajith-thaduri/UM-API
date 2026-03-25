"""Unit tests for upload intake LangGraph (routing, nodes, serialization, full invoke paths)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.upload_agent_graph import (
    UploadAgentGraphRunner,
    UploadGraphState,
    agent_dict_to_message,
    build_upload_graph,
    invoke_upload_message,
)
from app.services.upload_agent_service import (
    AgentMessage,
    ConversationState,
    MessageType,
    QuickAction,
    upload_agent_service,
)


def _fake_session(
    state: str,
    *,
    messages: list | None = None,
    case_id: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.state = state
    s.messages = [] if messages is None else list(messages)
    s.case_id = case_id
    s.id = "sess-1"
    s.updated_at = None
    s.processing_status = None
    return s


def _minimal_agent_dict(**overrides) -> dict:
    base = {
        "id": "am-1",
        "message": "hello",
        "type": "question",
        "timestamp": "2025-01-01T00:00:00",
        "actions": [],
        "suggestions": [],
        "field": None,
        "extracted_data": None,
        "files_info": None,
        "progress": None,
    }
    base.update(overrides)
    return base


# --- agent_dict_to_message ---


def test_agent_dict_to_message_minimal():
    d = _minimal_agent_dict()
    m = agent_dict_to_message(d)
    assert m.id == "am-1"
    assert m.message == "hello"
    assert m.type == MessageType.QUESTION
    assert m.actions == []
    assert m.suggestions == []


def test_agent_dict_to_message_actions_from_dicts():
    d = _minimal_agent_dict(
        actions=[{"label": "Go", "value": "go", "variant": "primary"}],
    )
    m = agent_dict_to_message(d)
    assert len(m.actions) == 1
    assert m.actions[0].label == "Go"
    assert m.actions[0].value == "go"
    assert m.actions[0].variant == "primary"


def test_agent_dict_to_message_actions_quickaction_instances():
    qa = QuickAction(label="X", value="x", variant="default")
    d = _minimal_agent_dict(actions=[qa])
    m = agent_dict_to_message(d)
    assert m.actions == [qa]


def test_agent_dict_to_message_type_already_enum():
    d = _minimal_agent_dict()
    d["type"] = MessageType.ERROR
    m = agent_dict_to_message(d)
    assert m.type == MessageType.ERROR


def test_agent_dict_to_message_suggestions_and_optional_fields():
    d = _minimal_agent_dict(
        suggestions=["a", "b"],
        field="patient_name",
        extracted_data={"patient_name": "P"},
        files_info=[{"name": "f.pdf"}],
        progress=50,
    )
    m = agent_dict_to_message(d)
    assert m.suggestions == ["a", "b"]
    assert m.current_field == "patient_name"
    assert m.extracted_data == {"patient_name": "P"}
    assert m.files_info == [{"name": "f.pdf"}]
    assert m.progress == 50


def test_agent_dict_to_message_invalid_type_raises():
    d = _minimal_agent_dict(type="not_a_valid_message_type")
    with pytest.raises(ValueError):
        agent_dict_to_message(d)


# --- routing ---


@pytest.mark.parametrize(
    "conversation_state,expected",
    [
        (ConversationState.WAITING_FOR_FILES.value, "waiting_files"),
        (ConversationState.CONFIRM_ANALYSIS.value, "confirm_analysis"),
        (ConversationState.REVIEW_SUMMARY.value, "review_summary"),
        (ConversationState.PROCESSING.value, "terminal_guard"),
        (ConversationState.COMPLETE.value, "terminal_guard"),
        (ConversationState.ERROR.value, "terminal_guard"),
        (ConversationState.COLLECTING_DATA.value, "llm_collect"),
        (ConversationState.GREETING.value, "llm_collect"),
        ("", "llm_collect"),
        ("unknown_custom_state", "llm_collect"),
    ],
)
def test_route_after_append_by_state(conversation_state, expected):
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "hi")
    state: UploadGraphState = {"conversation_state": conversation_state}
    assert runner.route_after_append(state) == expected


def test_route_after_append_done_when_agent_output():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "hi")
    state: UploadGraphState = {
        "conversation_state": ConversationState.WAITING_FOR_FILES.value,
        "agent_output": _minimal_agent_dict(message="err"),
    }
    assert runner.route_after_append(state) == "done"


@pytest.mark.parametrize(
    "has_output,expected",
    [
        (True, "done"),
        (False, "llm_collect"),
    ],
)
def test_route_after_review_summary(has_output, expected):
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "hi")
    state: UploadGraphState = {}
    if has_output:
        state["agent_output"] = _minimal_agent_dict()
    assert runner.route_after_review_summary(state) == expected


def test_build_upload_graph_compiles():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "m")
    g = build_upload_graph(runner)
    assert g is not None
    assert hasattr(g, "ainvoke")


# --- async nodes (mocked service) ---


@pytest.mark.asyncio
async def test_node_append_user_session_missing():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "missing", "hi")
    with patch.object(upload_agent_service, "get_session", return_value=None):
        out = await runner.node_append_user(
            {"session_id": "missing", "user_message": "hi"}
        )
    assert "agent_output" in out
    assert "Session not found" in out["agent_output"]["message"]
    assert out["agent_output"]["type"] == "error"
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_node_append_user_appends_user_and_returns_state():
    db = MagicMock()
    session = _fake_session(ConversationState.COLLECTING_DATA.value, messages=[])
    runner = UploadAgentGraphRunner(db, session.id, "Hello")
    with patch.object(upload_agent_service, "get_session", return_value=session):
        out = await runner.node_append_user(
            {"session_id": session.id, "user_message": "Hello"}
        )
    assert out == {"conversation_state": ConversationState.COLLECTING_DATA.value}
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["message"] == "Hello"
    db.commit.assert_called()
    db.refresh.assert_called_once_with(session)


@pytest.mark.asyncio
async def test_node_waiting_files_session_missing():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "x", "m")
    with patch.object(upload_agent_service, "get_session", return_value=None):
        out = await runner.node_waiting_files({"session_id": "x", "user_message": "m"})
    assert "Session not found" in out["agent_output"]["message"]


@pytest.mark.asyncio
async def test_node_waiting_files_persists_agent_reply():
    db = MagicMock()
    session = _fake_session(ConversationState.WAITING_FOR_FILES.value, messages=[])
    runner = UploadAgentGraphRunner(db, "sid", "m")
    with patch.object(upload_agent_service, "get_session", return_value=session):
        out = await runner.node_waiting_files({"session_id": "sid", "user_message": "m"})
    assert "upload" in out["agent_output"]["message"].lower()
    assert out["agent_output"]["type"] == "question"
    assert any(m.get("role") == "agent" for m in session.messages)


@pytest.mark.asyncio
async def test_node_confirm_analysis_missing_session():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "m")
    with patch.object(upload_agent_service, "get_session", return_value=None):
        out = await runner.node_confirm_analysis({"session_id": "sid", "user_message": "m"})
    assert "Session not found" in out["agent_output"]["message"]


@pytest.mark.asyncio
async def test_node_confirm_analysis_sets_collecting_data():
    db = MagicMock()
    session = _fake_session(ConversationState.CONFIRM_ANALYSIS.value)
    runner = UploadAgentGraphRunner(db, "sid", "yes")
    with patch.object(upload_agent_service, "get_session", return_value=session):
        out = await runner.node_confirm_analysis({"session_id": "sid", "user_message": "yes"})
    assert out == {}
    assert session.state == ConversationState.COLLECTING_DATA.value
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_node_review_summary_missing_session():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "start")
    with patch.object(upload_agent_service, "get_session", return_value=None):
        out = await runner.node_review_summary({"session_id": "sid", "user_message": "start"})
    assert "Session not found" in out["agent_output"]["message"]


@pytest.mark.asyncio
async def test_node_review_summary_start_keyword_calls_start_processing():
    db = MagicMock()
    session = _fake_session(ConversationState.REVIEW_SUMMARY.value)
    runner = UploadAgentGraphRunner(db, "sid", "Start Processing")
    start_msg = AgentMessage(
        id="sp-1",
        message="Starting now!",
        type=MessageType.STATUS,
        timestamp="t",
        progress=0,
    )
    with patch.object(upload_agent_service, "get_session", return_value=session), patch.object(
        upload_agent_service,
        "_start_processing_message",
        return_value=start_msg,
    ) as mock_start:
        out = await runner.node_review_summary(
            {"session_id": "sid", "user_message": "Start Processing"}
        )
    mock_start.assert_called_once_with(db, session)
    assert out["agent_output"]["message"] == "Starting now!"


@pytest.mark.parametrize(
    "user_text",
    [
        "yes",
        "YES",
        "  go  ",
        "looks good",
        "yes, looks good",
        "start processing",
    ],
)
@pytest.mark.asyncio
async def test_node_review_summary_start_keywords_variants(user_text):
    db = MagicMock()
    session = _fake_session(ConversationState.REVIEW_SUMMARY.value)
    runner = UploadAgentGraphRunner(db, "sid", user_text)
    start_msg = AgentMessage(
        id="sp-2",
        message="ok",
        type=MessageType.STATUS,
        timestamp="t",
        progress=0,
    )
    with patch.object(upload_agent_service, "get_session", return_value=session), patch.object(
        upload_agent_service, "_start_processing_message", return_value=start_msg
    ):
        out = await runner.node_review_summary(
            {"session_id": "sid", "user_message": user_text}
        )
    assert out["agent_output"]["message"] == "ok"


@pytest.mark.asyncio
async def test_node_review_summary_non_start_goes_back_to_collecting():
    db = MagicMock()
    session = _fake_session(ConversationState.REVIEW_SUMMARY.value)
    runner = UploadAgentGraphRunner(db, "sid", "Change the MRN please")
    with patch.object(upload_agent_service, "get_session", return_value=session):
        out = await runner.node_review_summary(
            {"session_id": "sid", "user_message": "Change the MRN please"}
        )
    assert out == {}
    assert session.state == ConversationState.COLLECTING_DATA.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_state,expected_substring",
    [
        (ConversationState.PROCESSING.value, "already processing"),
        (ConversationState.COMPLETE.value, "complete"),
        (ConversationState.ERROR.value, "error"),
    ],
)
async def test_node_terminal_guard_messages(terminal_state, expected_substring):
    db = MagicMock()
    session = _fake_session(terminal_state, case_id=None)
    runner = UploadAgentGraphRunner(db, "sid", "m")
    with patch.object(upload_agent_service, "get_session", return_value=session):
        out = await runner.node_terminal_guard({"session_id": "sid", "user_message": "m"})
    assert expected_substring in out["agent_output"]["message"].lower()
    assert out["agent_output"]["type"] == "question"


@pytest.mark.asyncio
async def test_node_terminal_guard_view_case_when_case_id():
    db = MagicMock()
    session = _fake_session(ConversationState.PROCESSING.value, case_id="case-99")
    runner = UploadAgentGraphRunner(db, "sid", "m")
    with patch.object(upload_agent_service, "get_session", return_value=session):
        out = await runner.node_terminal_guard({"session_id": "sid", "user_message": "m"})
    actions = out["agent_output"]["actions"]
    assert any(a.get("value") == "view_case:case-99" for a in actions)


@pytest.mark.asyncio
async def test_node_terminal_guard_session_missing():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "m")
    with patch.object(upload_agent_service, "get_session", return_value=None):
        out = await runner.node_terminal_guard({"session_id": "sid", "user_message": "m"})
    assert "Session not found" in out["agent_output"]["message"]


@pytest.mark.asyncio
async def test_node_llm_collect_missing_session():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "m")
    with patch.object(upload_agent_service, "get_session", return_value=None):
        out = await runner.node_llm_collect({"session_id": "sid", "user_message": "m"})
    assert "Session not found" in out["agent_output"]["message"]


@pytest.mark.asyncio
async def test_node_llm_collect_delegates_to_generate():
    db = MagicMock()
    session = _fake_session(ConversationState.COLLECTING_DATA.value)
    runner = UploadAgentGraphRunner(db, "sid", "m")
    llm_msg = AgentMessage(
        id="llm-1",
        message="What is the MRN?",
        type=MessageType.QUESTION,
        timestamp="t",
    )
    with patch.object(upload_agent_service, "get_session", return_value=session), patch.object(
        upload_agent_service,
        "_generate_and_save_agent_response",
        new_callable=AsyncMock,
        return_value=llm_msg,
    ) as mock_gen:
        out = await runner.node_llm_collect({"session_id": "sid", "user_message": "m"})
    mock_gen.assert_awaited_once_with(db, session)
    assert out["agent_output"]["message"] == "What is the MRN?"


# --- end-to-end invoke (mocked) ---


@pytest.mark.asyncio
async def test_invoke_upload_message_waiting_for_files_short_circuit():
    db = MagicMock()
    session = _fake_session(ConversationState.WAITING_FOR_FILES.value, messages=[])
    with patch.object(upload_agent_service, "get_session", return_value=session):
        result = await invoke_upload_message(db, "sid", "any")
    assert "pdf" in result.message.lower()
    assert result.type == MessageType.QUESTION


@pytest.mark.asyncio
async def test_invoke_upload_message_collecting_data_hits_llm_node():
    db = MagicMock()
    session = _fake_session(ConversationState.COLLECTING_DATA.value, messages=[])
    llm_msg = AgentMessage(
        id="l2",
        message="Need DOB",
        type=MessageType.QUESTION,
        timestamp="t",
    )
    with patch.object(upload_agent_service, "get_session", return_value=session), patch.object(
        upload_agent_service,
        "_generate_and_save_agent_response",
        new_callable=AsyncMock,
        return_value=llm_msg,
    ):
        result = await invoke_upload_message(db, "sid", "user turn")
    assert result.message == "Need DOB"


@pytest.mark.asyncio
async def test_invoke_upload_message_unknown_session():
    db = MagicMock()
    with patch.object(upload_agent_service, "get_session", return_value=None):
        result = await invoke_upload_message(db, "nope", "hi")
    assert "Session not found" in result.message
    assert result.type == MessageType.ERROR


@pytest.mark.asyncio
async def test_runner_run_returns_generic_error_when_no_agent_output():
    db = MagicMock()
    runner = UploadAgentGraphRunner(db, "sid", "m")
    mock_compiled = MagicMock()
    mock_compiled.ainvoke = AsyncMock(return_value={})
    with patch(
        "app.services.upload_agent_graph.build_upload_graph",
        return_value=mock_compiled,
    ):
        result = await runner.run()
    assert "Something went wrong" in result.message
    assert result.type == MessageType.ERROR


@pytest.mark.asyncio
async def test_invoke_confirm_analysis_then_llm():
    db = MagicMock()
    session = _fake_session(ConversationState.CONFIRM_ANALYSIS.value, messages=[])
    llm_msg = AgentMessage(
        id="l3",
        message="Next question",
        type=MessageType.QUESTION,
        timestamp="t",
    )

    def get_sess(_db, sid):
        return session

    with patch.object(upload_agent_service, "get_session", side_effect=get_sess), patch.object(
        upload_agent_service,
        "_generate_and_save_agent_response",
        new_callable=AsyncMock,
        return_value=llm_msg,
    ):
        result = await invoke_upload_message(db, "sid", "yes")
    assert session.state == ConversationState.COLLECTING_DATA.value
    assert result.message == "Next question"


@pytest.mark.asyncio
async def test_invoke_review_summary_edit_then_llm():
    db = MagicMock()
    session = _fake_session(ConversationState.REVIEW_SUMMARY.value, messages=[])
    llm_msg = AgentMessage(
        id="l4",
        message="Updated",
        type=MessageType.QUESTION,
        timestamp="t",
    )
    with patch.object(upload_agent_service, "get_session", return_value=session), patch.object(
        upload_agent_service,
        "_generate_and_save_agent_response",
        new_callable=AsyncMock,
        return_value=llm_msg,
    ):
        result = await invoke_upload_message(db, "sid", "fix the patient name")
    assert result.message == "Updated"
    assert session.state == ConversationState.COLLECTING_DATA.value


@pytest.mark.asyncio
async def test_invoke_review_summary_start_processing():
    db = MagicMock()
    session = _fake_session(ConversationState.REVIEW_SUMMARY.value, messages=[])
    start_msg = AgentMessage(
        id="s1",
        message="Starting now! I'll extract",
        type=MessageType.STATUS,
        timestamp="t",
        progress=0,
    )
    with patch.object(upload_agent_service, "get_session", return_value=session), patch.object(
        upload_agent_service,
        "_start_processing_message",
        return_value=start_msg,
    ):
        result = await invoke_upload_message(db, "sid", "confirm")
    assert "Starting now" in result.message
    assert result.type == MessageType.STATUS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,needle",
    [
        (ConversationState.PROCESSING.value, "processing"),
        (ConversationState.COMPLETE.value, "complete"),
        (ConversationState.ERROR.value, "error"),
    ],
)
async def test_invoke_terminal_states(state, needle):
    db = MagicMock()
    session = _fake_session(state, messages=[])
    with patch.object(upload_agent_service, "get_session", return_value=session):
        result = await invoke_upload_message(db, "sid", "hello again")
    assert needle in result.message.lower()
