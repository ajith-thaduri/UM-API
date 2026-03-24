"""
LangGraph-based case agent: explicit nodes, stream-friendly updates.
Tier-1 LLM only; Claude artifacts preloaded from DB via case context bundle.
"""

from __future__ import annotations

import json
import logging
import operator
from typing import Annotated, Any, AsyncIterator, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.services.case_agent_context_service import build_case_agent_context
from app.services.case_agent_service import (
    CaseAgentRunResult,
    LLMCaller,
    _build_sources_from_rag,
    _extract_suggested_actions,
    _try_deterministic_answer,
    build_compare_enrichment,
    classify_intent,
    context_aware_suggestions,
    retrieval_policy,
    should_retry_with_retrieval,
)

# Intents where execution steps add no value for the user
_SIMPLE_INTENTS = frozenset({"greeting", "assistant_identity", "version_count", "live_version"})
from app.services.prompt_service import prompt_service
from app.services.rag_retriever import rag_retriever

logger = logging.getLogger(__name__)


def _step(
    sid: str,
    label: str,
    status: str = "done",
    detail: Optional[str] = None,
    tool: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": sid, "label": label, "status": status}
    if detail:
        row["detail"] = detail
    if tool:
        row["tool"] = tool
    return row


class CaseAgentState(TypedDict, total=False):
    trace_steps: List[Dict[str, Any]]
    resolved_intent: str
    short_circuit: bool
    show_trace: bool
    answer: str
    confidence: float
    sources: List[Dict[str, Any]]
    chunks_used: List[str]
    structured_blocks: Optional[Dict[str, Any]]
    used_artifacts: List[str]
    active_version_summary: Optional[Dict[str, Any]]
    context_summary: Optional[str]
    suggested_actions: List[str]


class CaseAgentGraphRunner:
    """Binds DB session + LLM for one request; nodes read/write LangGraph state."""

    def __init__(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        question: str,
        history_text: str,
        include_dashboard_context: bool,
        case_version_id: Optional[str],
        llm_answer_fn: LLMCaller,
    ):
        self.db = db
        self.case_id = case_id
        self.user_id = user_id
        self.question = question
        self.history_text = history_text
        self.include_dashboard_context = include_dashboard_context
        self.case_version_id = case_version_id
        self.llm_answer_fn = llm_answer_fn
        self.ctx: Any = None
        self.intent: str = "general_case_qa"
        self._revision_extra: str = ""
        self._rag_context: Any = None

    async def node_load_context(self, state: CaseAgentState) -> Dict[str, Any]:
        self.ctx = build_case_agent_context(self.db, self.case_id, self.user_id, self.case_version_id)
        if not self.ctx:
            return {
                "trace_steps": [
                    _step("load_case", "Reading case and selected version", tool="load_case_context"),
                    _step("error", "Context load failed", "error"),
                ],
                "short_circuit": True,
                "answer": "Case or version context could not be loaded.",
                "confidence": 0.0,
                "sources": [],
                "chunks_used": [],
                "resolved_intent": "error",
            }
        has_revision = bool(self.ctx.revision_impact_report or self.ctx.change_summary)
        active_summary = {
            "selected_version_number": self.ctx.selected_version_number,
            "live_version_number": self.ctx.live_version_number,
            "is_on_live": self.ctx.is_on_live,
            "version_count": self.ctx.version_count,
            "has_revision_impact": has_revision,
        }
        return {
            "trace_steps": [
                _step("load_case", "Reading case and selected version", tool="load_case_context"),
                _step("load_versions", "Checking live version and lineage", tool="load_version_context"),
            ],
            "active_version_summary": active_summary,
            "sources": [],
            "chunks_used": [],
        }

    async def node_classify(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        self.intent = classify_intent(self.question)
        det_answer, structured_blocks = _try_deterministic_answer(self.question, self.ctx, self.intent)
        trace = [
            _step(
                "intent",
                f"Classified intent: {self.intent.replace('_', ' ')}",
                tool="classify_intent",
                detail=self.intent,
            )
        ]
        if det_answer is not None:
            self.ctx.used_artifact_keys.extend(
                [k for k in ["version_metadata"] if k not in self.ctx.used_artifact_keys]
            )
            is_simple = self.intent in _SIMPLE_INTENTS
            if not is_simple:
                trace.append(_step("compose", "Composing grounded answer", tool="answer_composer"))
            used = list(dict.fromkeys(self.ctx.used_artifact_keys))
            return {
                "trace_steps": trace,
                "resolved_intent": self.intent,
                "short_circuit": True,
                "show_trace": not is_simple,
                "answer": det_answer,
                "confidence": 0.95,
                "structured_blocks": structured_blocks,
                "suggested_actions": context_aware_suggestions(
                    self.intent, self.ctx, det_answer, self.question
                ),
                "context_summary": f"v{self.ctx.selected_version_number} selected; {self.ctx.version_count} versions total.",
                "used_artifacts": used,
            }
        return {
            "trace_steps": trace,
            "resolved_intent": self.intent,
        }

    async def node_load_artifacts(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        trace = [
            _step(
                "load_artifacts",
                "Loading case Context",
                tool="load_case_context_artifacts",
                detail="Claude-generated case context and version artifacts",
            )
        ]
        out: Dict[str, Any] = {"trace_steps": trace}
        if self.intent in ("revision_diff", "compare_versions"):
            extra, block = build_compare_enrichment(
                self.db,
                self.case_id,
                self.user_id,
                self.question,
                self.ctx,
                intent=self.intent,
            )
            self._revision_extra = extra
            if block:
                merged = {**(state.get("structured_blocks") or {}), **block}
                out["structured_blocks"] = merged
        else:
            self._revision_extra = ""
        return out

    async def node_retrieve(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        used_det = False
        retrieve, reason = retrieval_policy(self.intent, self.question, used_det)
        if retrieve:
            trace = [
                _step(
                    "retrieve",
                    "Searching evidence chunks",
                    tool="retrieve_chunks",
                    detail=reason,
                )
            ]
            try:
                chunks = rag_retriever.retrieve_for_query(
                    db=self.db,
                    query=self.question,
                    case_id=self.case_id,
                    user_id=self.user_id,
                    top_k=8,
                    use_adaptive=False,
                    case_version_id=self.ctx.selected_version_id,
                )
                rag_context = rag_retriever.build_context(chunks, max_tokens=4000) if chunks else None
            except Exception as e:
                logger.warning("Case agent RAG retrieve failed: %s", e)
                rag_context = None
            if rag_context:
                self._rag_context = rag_context
                return {
                    "trace_steps": trace,
                    "sources": _build_sources_from_rag(rag_context),
                    "chunks_used": [c.chunk_id for c in rag_context.chunks],
                }
            self._rag_context = None
            return {
                "trace_steps": [
                    _step(
                        "retrieve",
                        "No chunks returned for this query",
                        "done",
                        tool="retrieve_chunks",
                        detail=reason,
                    )
                ],
                "sources": [],
                "chunks_used": [],
            }
        self._rag_context = None
        return {
            "trace_steps": [
                _step(
                    "retrieve",
                    "Skipped embedding search (case Context first)",
                    "skipped",
                    tool="retrieve_chunks",
                    detail=reason,
                )
            ],
            "sources": [],
            "chunks_used": [],
        }

    async def node_compose(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        trace = [_step("compose", "Composing grounded answer", tool="answer_composer")]
        sections = self.ctx.to_prompt_sections()
        extra = getattr(self, "_revision_extra", "") or ""
        if extra:
            sections += extra
        if not self.include_dashboard_context:
            sections = (
                "=== VERSION_METADATA (minimal; dashboard context omitted by request) ===\n"
                f"Selected v{self.ctx.selected_version_number}; live v{self.ctx.live_version_number}; "
                f"versions: {self.ctx.version_count}\n"
            )
        rag_context = getattr(self, "_rag_context", None)
        formatted_context = rag_context.formatted_context if rag_context else ""
        variables = {
            "question": self.question,
            "history_text": self.history_text or "No previous conversation",
            "structured_case_context": sections,
            "formatted_context": formatted_context or "No retrieved chunks for this turn.",
            "intent_hint": self.intent,
        }
        prompt_id = "case_agent_answer"
        fallback_template = """User question: {question}

Prior conversation:
{history_text}

Case Context (primary source):
{structured_case_context}

Retrieved evidence chunks (only for source/page grounding or when Case Context is insufficient):
{formatted_context}

Classified intent hint: {intent_hint}

Answer using ONLY the case materials above.
Start with Case Context first. Only rely on retrieved chunks when the user asks for evidence/page/source grounding or when Case Context is insufficient.
If the answer is not present in Case Context and no retrieved chunks are provided, say "Not documented in the case Context."
For version questions, prefer VERSION_METADATA and revision_impact_report over vague guesses.
For compare/both-versions questions, structure the answer with clear per-version sections (e.g. v1 vs v2) when two versions appear in context.
State whether key claims come from version metadata, case Context artifacts, or retrieved chunks.
"""
        try:
            prompt = prompt_service.render_prompt(prompt_id, variables)
        except Exception:
            prompt = fallback_template.format(**variables)
        if not prompt or not str(prompt).strip():
            prompt = fallback_template.format(**variables)

        system_message = prompt_service.get_system_message(prompt_id)
        if not system_message:
            system_message = (
                "You are a clinical AI assistant for utilization management review. "
                "Treat the provided Case Context as the primary source of truth. "
                "Use retrieved chunks only for page/source grounding or when Case Context is insufficient. "
                "Never fabricate clinical facts. Be concise and precise."
            )

        answer, confidence = await self.llm_answer_fn(
            prompt,
            prompt_id=prompt_id,
            db=self.db,
            user_id=self.user_id,
            case_id=self.case_id,
            system_message_override=system_message,
        )
        extra_trace: List[Dict[str, Any]] = []
        if not rag_context and should_retry_with_retrieval(self.intent, self.question, answer):
            extra_trace.append(
                _step(
                    "retrieve_retry",
                    "Case Context was insufficient; searching evidence chunks",
                    tool="retrieve_chunks",
                    detail="Fallback to embeddings only because the case Context did not answer the question",
                )
            )
            try:
                chunks = rag_retriever.retrieve_for_query(
                    db=self.db,
                    query=self.question,
                    case_id=self.case_id,
                    user_id=self.user_id,
                    top_k=8,
                    use_adaptive=False,
                    case_version_id=self.ctx.selected_version_id,
                )
                rag_context = rag_retriever.build_context(chunks, max_tokens=4000) if chunks else None
            except Exception as e:
                logger.warning("Case agent fallback RAG retrieve failed: %s", e)
                rag_context = None
            if rag_context:
                self._rag_context = rag_context
                variables["formatted_context"] = rag_context.formatted_context
                try:
                    prompt = prompt_service.render_prompt(prompt_id, variables)
                except Exception:
                    prompt = fallback_template.format(**variables)
                if not prompt or not str(prompt).strip():
                    prompt = fallback_template.format(**variables)
                answer, confidence = await self.llm_answer_fn(
                    prompt,
                    prompt_id=prompt_id,
                    db=self.db,
                    user_id=self.user_id,
                    case_id=self.case_id,
                    system_message_override=system_message,
                )
        blocks = dict(state.get("structured_blocks") or {})
        if self.intent == "contradictions" and self.ctx.contradictions_count:
            blocks["contradictions"] = {
                "count": self.ctx.contradictions_count,
                "preview": self.ctx.contradictions[:5] if self.ctx.contradictions else [],
            }
        self.ctx.register_artifact("tier1_completion")
        return {
            "trace_steps": trace + extra_trace,
            "answer": answer,
            "confidence": confidence,
            "sources": _build_sources_from_rag(rag_context) if rag_context else state.get("sources"),
            "chunks_used": [c.chunk_id for c in rag_context.chunks] if rag_context else state.get("chunks_used"),
            "structured_blocks": blocks if blocks else state.get("structured_blocks"),
        }

    async def node_finalize(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("resolved_intent") == "error":
            return {}
        ans = state.get("answer") or ""
        sug = _extract_suggested_actions(ans, self.question)
        used = [x for x in (self.ctx.used_artifact_keys if self.ctx else []) if x != "tier1_completion"]
        if state.get("chunks_used"):
            used.append("retrieved_evidence")
        used = list(dict.fromkeys(used))
        return {
            "suggested_actions": sug,
            "context_summary": state.get("context_summary")
            or f"Intent={state.get('resolved_intent')}; v{getattr(self.ctx, 'selected_version_number', '?')}; graph complete.",
            "used_artifacts": used,
        }


def _route_after_load(state: CaseAgentState) -> str:
    return "finalize" if state.get("short_circuit") else "classify"


def _route_after_classify(state: CaseAgentState) -> str:
    return "finalize" if state.get("short_circuit") else "artifacts"


def build_case_agent_graph(runner: CaseAgentGraphRunner) -> Any:
    """Compile LangGraph workflow for one runner instance."""

    class FullState(TypedDict, total=False):
        trace_steps: Annotated[List[Dict[str, Any]], operator.add]
        resolved_intent: str
        short_circuit: bool
        show_trace: bool
        answer: str
        confidence: float
        sources: List[Dict[str, Any]]
        chunks_used: List[str]
        structured_blocks: Optional[Dict[str, Any]]
        used_artifacts: List[str]
        active_version_summary: Optional[Dict[str, Any]]
        context_summary: Optional[str]
        suggested_actions: List[str]

    workflow = StateGraph(FullState)
    workflow.add_node("load", runner.node_load_context)
    workflow.add_node("classify", runner.node_classify)
    workflow.add_node("artifacts", runner.node_load_artifacts)
    workflow.add_node("retrieve", runner.node_retrieve)
    workflow.add_node("compose", runner.node_compose)
    workflow.add_node("finalize", runner.node_finalize)

    workflow.set_entry_point("load")
    workflow.add_conditional_edges(
        "load",
        _route_after_load,
        {"finalize": "finalize", "classify": "classify"},
    )
    workflow.add_conditional_edges(
        "classify",
        _route_after_classify,
        {"finalize": "finalize", "artifacts": "artifacts"},
    )
    workflow.add_edge("artifacts", "retrieve")
    workflow.add_edge("retrieve", "compose")
    workflow.add_edge("compose", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()


def _state_to_result(state: CaseAgentState, runner: CaseAgentGraphRunner) -> CaseAgentRunResult:
    return CaseAgentRunResult(
        answer=state.get("answer") or "",
        sources=state.get("sources") or [],
        chunks_used=state.get("chunks_used") or [],
        confidence=float(state.get("confidence") or 0.0),
        suggested_actions=state.get("suggested_actions") or [],
        trace_steps=state.get("trace_steps") or [],
        context_summary=state.get("context_summary"),
        active_version_summary=state.get("active_version_summary"),
        used_artifacts=state.get("used_artifacts") or [],
        structured_blocks=state.get("structured_blocks"),
        resolved_intent=state.get("resolved_intent"),
        show_trace=bool(state.get("show_trace", True)),
    )


async def invoke_case_agent_graph(
    db: Session,
    case_id: str,
    user_id: str,
    question: str,
    history_text: str,
    include_dashboard_context: bool,
    case_version_id: Optional[str],
    llm_answer_fn: LLMCaller,
) -> CaseAgentRunResult:
    runner = CaseAgentGraphRunner(
        db, case_id, user_id, question, history_text, include_dashboard_context, case_version_id, llm_answer_fn
    )
    graph = build_case_agent_graph(runner)
    initial: CaseAgentState = {"trace_steps": []}
    final = await graph.ainvoke(initial)
    return _state_to_result(final, runner)


async def astream_case_agent_graph(
    db: Session,
    case_id: str,
    user_id: str,
    question: str,
    history_text: str,
    include_dashboard_context: bool,
    case_version_id: Optional[str],
    llm_answer_fn: LLMCaller,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream NDJSON-friendly events. Yields trace_delta then a final payload.
    """
    runner = CaseAgentGraphRunner(
        db, case_id, user_id, question, history_text, include_dashboard_context, case_version_id, llm_answer_fn
    )
    graph = build_case_agent_graph(runner)
    initial: CaseAgentState = {"trace_steps": []}
    prev_len = 0
    last_state: Dict[str, Any] = {}

    async for state in graph.astream(initial, stream_mode="values"):
        last_state = state
        steps = state.get("trace_steps") or []
        if len(steps) > prev_len:
            yield {"type": "trace_delta", "steps": steps[prev_len:]}
            prev_len = len(steps)

    final = _state_to_result(last_state, runner)
    yield {
        "type": "final",
        "answer": final.answer,
        "sources": final.sources,
        "chunks_used": final.chunks_used,
        "confidence": final.confidence,
        "suggested_actions": final.suggested_actions,
        "trace_steps": final.trace_steps,
        "context_summary": final.context_summary,
        "active_version_summary": final.active_version_summary,
        "used_artifacts": final.used_artifacts,
        "structured_blocks": final.structured_blocks,
        "resolved_intent": final.resolved_intent,
        "show_trace": final.show_trace,
    }
