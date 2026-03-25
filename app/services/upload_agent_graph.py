"""
LangGraph orchestration for the upload intake agent (Phase 2b).

Replaces ad-hoc branching in `process_message` with explicit nodes and edges:
  append_user → route → (waiting_files | confirm_analysis | review_summary | terminal_guard | llm_collect) → END

LLM extraction, summary, and start-processing behaviors remain in `UploadAgentService` as shared helpers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.services.upload_agent_service import (
    AgentMessage,
    ConversationState,
    MessageType,
    QuickAction,
    UserMessage,
    upload_agent_service,
)

logger = logging.getLogger(__name__)


class UploadGraphState(TypedDict, total=False):
    session_id: str
    user_message: str
    conversation_state: str
    """Serialized `AgentMessage.to_dict()` when the graph is done."""
    agent_output: Dict[str, Any]


def agent_dict_to_message(d: Dict[str, Any]) -> AgentMessage:
    raw_actions = d.get("actions") or []
    actions: List[QuickAction] = []
    for a in raw_actions:
        if isinstance(a, QuickAction):
            actions.append(a)
        else:
            actions.append(
                QuickAction(
                    label=a.get("label", ""),
                    value=a.get("value", ""),
                    variant=a.get("variant", "default"),
                )
            )
    return AgentMessage(
        id=d["id"],
        message=d["message"],
        type=MessageType(d["type"]) if isinstance(d["type"], str) else d["type"],
        timestamp=d["timestamp"],
        actions=actions,
        suggestions=list(d.get("suggestions") or []),
        current_field=d.get("field"),
        extracted_data=d.get("extracted_data"),
        files_info=d.get("files_info"),
        progress=d.get("progress"),
    )


_START_PROCESSING_KEYWORDS = frozenset(
    {
        "yes",
        "yes, looks good",
        "start",
        "process",
        "start processing",
        "confirm",
        "go",
        "looks good",
    }
)


class UploadAgentGraphRunner:
    """Runs one user text turn through the upload LangGraph."""

    def __init__(self, db: Session, session_id: str, user_message: str) -> None:
        self.db = db
        self.session_id = session_id
        self.user_message = user_message

    async def node_append_user(self, state: UploadGraphState) -> Dict[str, Any]:
        session = upload_agent_service.get_session(self.db, state["session_id"])
        if not session:
            am = upload_agent_service._error_message("Session not found. Please start over.")
            return {"agent_output": am.to_dict()}

        user_msg = UserMessage(
            id=str(uuid.uuid4()),
            message=state["user_message"],
            timestamp=datetime.utcnow().isoformat(),
        )
        messages = list(session.messages or [])
        messages.append({"role": "user", **user_msg.to_dict()})
        session.messages = messages
        session.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(session)
        return {"conversation_state": session.state}

    def route_after_append(self, state: UploadGraphState) -> Literal[
        "done",
        "waiting_files",
        "confirm_analysis",
        "review_summary",
        "terminal_guard",
        "llm_collect",
    ]:
        if state.get("agent_output"):
            return "done"
        cs = state.get("conversation_state") or ""
        if cs == ConversationState.WAITING_FOR_FILES.value:
            return "waiting_files"
        if cs == ConversationState.CONFIRM_ANALYSIS.value:
            return "confirm_analysis"
        if cs == ConversationState.REVIEW_SUMMARY.value:
            return "review_summary"
        if cs in (
            ConversationState.PROCESSING.value,
            ConversationState.COMPLETE.value,
            ConversationState.ERROR.value,
        ):
            return "terminal_guard"
        return "llm_collect"

    async def node_waiting_files(self, state: UploadGraphState) -> Dict[str, Any]:
        session = upload_agent_service.get_session(self.db, state["session_id"])
        if not session:
            am = upload_agent_service._error_message("Session not found. Please start over.")
            return {"agent_output": am.to_dict()}

        agent_msg = AgentMessage(
            id=str(uuid.uuid4()),
            message="I'm waiting for you to upload some files first. Please upload your PDFs.",
            type=MessageType.QUESTION,
            timestamp=datetime.utcnow().isoformat(),
        )
        msgs = list(session.messages or [])
        msgs.append({"role": "agent", **agent_msg.to_dict()})
        session.messages = msgs
        session.updated_at = datetime.utcnow()
        self.db.commit()
        return {"agent_output": agent_msg.to_dict()}

    async def node_confirm_analysis(self, state: UploadGraphState) -> Dict[str, Any]:
        session = upload_agent_service.get_session(self.db, state["session_id"])
        if not session:
            am = upload_agent_service._error_message("Session not found. Please start over.")
            return {"agent_output": am.to_dict()}

        session.state = ConversationState.COLLECTING_DATA.value
        session.updated_at = datetime.utcnow()
        self.db.commit()
        return {}

    async def node_review_summary(self, state: UploadGraphState) -> Dict[str, Any]:
        session = upload_agent_service.get_session(self.db, state["session_id"])
        if not session:
            am = upload_agent_service._error_message("Session not found. Please start over.")
            return {"agent_output": am.to_dict()}

        msg_lower = state["user_message"].lower().strip()
        if msg_lower in _START_PROCESSING_KEYWORDS:
            am = upload_agent_service._start_processing_message(self.db, session)
            return {"agent_output": am.to_dict()}

        session.state = ConversationState.COLLECTING_DATA.value
        session.updated_at = datetime.utcnow()
        self.db.commit()
        return {}

    def route_after_review_summary(self, state: UploadGraphState) -> Literal["done", "llm_collect"]:
        if state.get("agent_output"):
            return "done"
        return "llm_collect"

    async def node_terminal_guard(self, state: UploadGraphState) -> Dict[str, Any]:
        session = upload_agent_service.get_session(self.db, state["session_id"])
        if not session:
            am = upload_agent_service._error_message("Session not found. Please start over.")
            return {"agent_output": am.to_dict()}

        cs = session.state
        actions: List[QuickAction] = []
        if session.case_id:
            actions.append(
                QuickAction(
                    label="View Case",
                    value=f"view_case:{session.case_id}",
                    variant="primary",
                )
            )

        if cs == ConversationState.ERROR.value:
            text = (
                "This session ended with an error. Start a new upload from the Upload page "
                "if you need to try again."
            )
        elif cs == ConversationState.COMPLETE.value:
            text = "This upload is complete. You can open the case below or start a new upload."
        else:
            text = (
                "This session is already processing. You can open the case below; "
                "please wait for processing to finish."
            )

        agent_msg = AgentMessage(
            id=str(uuid.uuid4()),
            message=text,
            type=MessageType.QUESTION,
            timestamp=datetime.utcnow().isoformat(),
            actions=actions,
        )
        msgs = list(session.messages or [])
        msgs.append({"role": "agent", **agent_msg.to_dict()})
        session.messages = msgs
        session.updated_at = datetime.utcnow()
        self.db.commit()
        return {"agent_output": agent_msg.to_dict()}

    async def node_llm_collect(self, state: UploadGraphState) -> Dict[str, Any]:
        session = upload_agent_service.get_session(self.db, state["session_id"])
        if not session:
            am = upload_agent_service._error_message("Session not found. Please start over.")
            return {"agent_output": am.to_dict()}

        am = await upload_agent_service._generate_and_save_agent_response(self.db, session)
        return {"agent_output": am.to_dict()}

    async def run(self) -> AgentMessage:
        graph = build_upload_graph(self)
        final = await graph.ainvoke(
            {
                "session_id": self.session_id,
                "user_message": self.user_message,
            }
        )
        out = final.get("agent_output")
        if not out:
            logger.error("Upload graph finished without agent_output session_id=%s", self.session_id)
            return upload_agent_service._error_message("Something went wrong. Please try again.")
        return agent_dict_to_message(out)


def build_upload_graph(runner: UploadAgentGraphRunner):
    graph = StateGraph(UploadGraphState)

    graph.add_node("append_user", runner.node_append_user)
    graph.add_node("waiting_files", runner.node_waiting_files)
    graph.add_node("confirm_analysis", runner.node_confirm_analysis)
    graph.add_node("review_summary", runner.node_review_summary)
    graph.add_node("terminal_guard", runner.node_terminal_guard)
    graph.add_node("llm_collect", runner.node_llm_collect)

    graph.set_entry_point("append_user")
    graph.add_conditional_edges(
        "append_user",
        runner.route_after_append,
        {
            "done": END,
            "waiting_files": "waiting_files",
            "confirm_analysis": "confirm_analysis",
            "review_summary": "review_summary",
            "terminal_guard": "terminal_guard",
            "llm_collect": "llm_collect",
        },
    )
    graph.add_edge("waiting_files", END)
    graph.add_edge("confirm_analysis", "llm_collect")
    graph.add_conditional_edges(
        "review_summary",
        runner.route_after_review_summary,
        {
            "done": END,
            "llm_collect": "llm_collect",
        },
    )
    graph.add_edge("terminal_guard", END)
    graph.add_edge("llm_collect", END)

    return graph.compile()


async def invoke_upload_message(db: Session, session_id: str, user_message: str) -> AgentMessage:
    """Public entry: run one upload-agent text turn via LangGraph."""
    runner = UploadAgentGraphRunner(db, session_id, user_message)
    return await runner.run()
