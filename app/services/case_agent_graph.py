"""
LangGraph-based case agent: narrative-first staged flow, stream-friendly updates.
Tier-1 LLM only; Tier-2 narrative is read from DB via CaseAgentContextBundle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import operator
import time
from typing import Annotated, Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, TypedDict

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
    build_evidence_search_plan,
    classify_intent,
    context_aware_suggestions,
    format_search_plan_for_prompt,
    should_retry_with_retrieval,
)

# Intents where execution steps add no value for the user
_SIMPLE_INTENTS = frozenset({"greeting", "assistant_identity", "version_count", "live_version"})
from app.services.prompt_service import prompt_service
from app.services.rag_retriever import rag_retriever

logger = logging.getLogger(__name__)

# Chat latency guardrails: lower retrieval fan-out and prompt context budget for interactive turns.
_CHAT_RETRIEVE_TOP_K = 12
_CHAT_MAX_CONTEXT_TOKENS = 2600


def _step(
    sid: str,
    label: str,
    status: str = "done",
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": sid, "label": label, "status": status}
    if detail:
        row["detail"] = detail
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
    need_retrieval: bool
    telemetry: Dict[str, Any]


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
        working_memory_text: str = "",
        on_answer_delta: Optional[Callable[[str], Awaitable[None] | None]] = None,
    ):
        self.db = db
        self.case_id = case_id
        self.user_id = user_id
        self.question = question
        self.history_text = history_text
        self.include_dashboard_context = include_dashboard_context
        self.case_version_id = case_version_id
        self.llm_answer_fn = llm_answer_fn
        self.working_memory_text = (working_memory_text or "").strip()
        self.on_answer_delta = on_answer_delta
        self.ctx: Any = None
        self.intent: str = "general_case_qa"
        self._revision_extra: str = ""
        self._rag_context: Any = None
        self._used_initial_retrieval: bool = False
        self._evidence_search_plan: Any = None

    async def node_load_context(self, state: CaseAgentState) -> Dict[str, Any]:
        self.ctx = build_case_agent_context(self.db, self.case_id, self.user_id, self.case_version_id)
        if not self.ctx:
            return {
                "trace_steps": [
                    _step("load_case", "Opening this case and version", "error"),
                    _step("error", "Could not load case context", "error"),
                ],
                "short_circuit": True,
                "answer": "Case or version context could not be loaded.",
                "confidence": 0.0,
                "sources": [],
                "chunks_used": [],
                "resolved_intent": "error",
                "telemetry": {"error": "context_load_failed"},
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
                _step("load_case", "Reading case and selected version"),
                _step("versions", "Checking version history"),
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
                "routing",
                "Understanding your question",
                detail=self.intent.replace("_", " "),
            )
        ]
        if det_answer is not None:
            self.ctx.used_artifact_keys.extend(
                [k for k in ["version_metadata"] if k not in self.ctx.used_artifact_keys]
            )
            is_simple = self.intent in _SIMPLE_INTENTS
            if not is_simple:
                trace.append(_step("compose", "Preparing answer"))
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
                "telemetry": {"provenance": "deterministic", "intent": self.intent},
            }
        return {
            "trace_steps": trace,
            "resolved_intent": self.intent,
        }

    async def node_narrative(self, state: CaseAgentState) -> Dict[str, Any]:
        """Load narrative-first context sections; compare/revision enrichment when needed."""
        if state.get("short_circuit"):
            return {}
        trace = [
            _step(
                "narrative",
                "Reading case summary",
                detail="Using the stored summary for this version as the main story",
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

    async def node_assess_evidence(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        plan = build_evidence_search_plan(
            self.intent, self.question, self.ctx, used_deterministic=False
        )
        self._evidence_search_plan = plan
        retrieve = plan.retrieval_required
        self._used_initial_retrieval = retrieve
        if retrieve:
            trace = [
                _step(
                    "plan_search",
                    "Planning document lookup",
                    detail=f"{plan.question_type.replace('_', ' ')} · {plan.retrieval_goal.replace('_', ' ')}",
                ),
                _step("assess_sources", "Finding supporting pages", detail=plan.retrieval_reason),
            ]
        else:
            trace = [
                _step("assess_sources", "Answering from the case summary first", detail=plan.retrieval_reason)
            ]
        return {
            "trace_steps": trace,
            "need_retrieval": retrieve,
        }

    async def node_retrieve(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        trace = [_step("retrieve", "Searching uploaded documents", detail="Matching your question to excerpts")]
        try:
            plan = self._evidence_search_plan
            if plan and plan.retrieval_required:
                chunks = rag_retriever.retrieve_for_evidence_search(
                    db=self.db,
                    primary_query=self.question,
                    case_id=self.case_id,
                    user_id=self.user_id,
                    case_version_id=self.ctx.selected_version_id,
                    embedding_query=plan.embedding_query,
                    top_k=_CHAT_RETRIEVE_TOP_K,
                    use_adaptive=False,
                    merge_lexical_matches=True,
                    extra_lexical_terms=plan.lexical_terms,
                )
            else:
                chunks = rag_retriever.retrieve_for_query(
                    db=self.db,
                    query=self.question,
                    case_id=self.case_id,
                    user_id=self.user_id,
                    top_k=_CHAT_RETRIEVE_TOP_K,
                    use_adaptive=False,
                    case_version_id=self.ctx.selected_version_id,
                    merge_lexical_matches=True,
                )
            rag_context = (
                rag_retriever.build_context(chunks, max_tokens=_CHAT_MAX_CONTEXT_TOKENS)
                if chunks
                else None
            )
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
                    "No matching document excerpts were found",
                    "done",
                    detail="You can ask about a specific page or section if needed",
                )
            ],
            "sources": [],
            "chunks_used": [],
        }

    def _compose_prompt_variables(self, formatted_context: str) -> Dict[str, Any]:
        assert self.ctx is not None
        plan = getattr(self, "_evidence_search_plan", None)
        nf = self.ctx.build_narrative_first_context(
            include_dashboard_context=self.include_dashboard_context,
            revision_compare_extra=self._revision_extra or "",
            search_plan_context=format_search_plan_for_prompt(plan),
        )
        wm = self.working_memory_text or "(No prior compressed memory for this version yet.)"
        return {
            "question": self.question,
            "history_text": self.history_text or "No previous conversation",
            "working_memory": wm,
            **nf,
            "formatted_context": formatted_context
            or "No supporting document excerpts retrieved for this turn.",
            "intent_hint": self.intent,
        }

    async def node_compose(self, state: CaseAgentState) -> Dict[str, Any]:
        if state.get("short_circuit"):
            return {}
        rag_context = getattr(self, "_rag_context", None)
        trace: List[Dict[str, Any]] = []
        if rag_context:
            trace.append(
                _step(
                    "evidence_compare",
                    "Comparing retrieved evidence with the summary",
                    detail="Ground document locations only in excerpts; keep clinical facts aligned with the summary",
                )
            )
        trace.append(_step("compose", "Preparing answer"))
        formatted_context = rag_context.formatted_context if rag_context else ""
        variables = self._compose_prompt_variables(formatted_context)

        prompt_id = "case_agent_answer"
        fallback_template = """User question: {question}

Prior conversation:
{history_text}

Version-scoped working memory (compressed; not a separate source of truth):
{working_memory}

{search_plan_context}

{authoritative_case_summary}

{version_and_lineage}

{review_artifacts}

{structured_clinical_facts}

{revision_compare_extra}

Supporting document excerpts:
{formatted_context}

Intent hint: {intent_hint}

Instructions:
- Understand the user question first, then use the stored case summary as the authoritative clinical story for this version.
- Follow DOCUMENT_SEARCH_PLAN above; it mirrors the server's tool workflow for this turn.
- For clinical facts, stay consistent with the summary. Do not contradict the summary.
- For document names, file numbers, or page numbers: state them only if they appear in the supporting excerpts below.
- When excerpts are provided, read them for the user's topic (including common medical synonyms). If an excerpt supports a location, cite it.
- If the summary mentions a topic but no excerpt shows a clear location, say the summary supports the topic but a matching page/document was not found in the retrieved excerpts.
- If the answer is not in the summary and excerpts do not help, say the information is not documented in the available materials for this version.
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
                "Use only the provided materials. The stored case summary is authoritative for clinical facts. "
                "Use document excerpts for page/file citations and for location questions; never invent a page or "
                "document reference. When excerpts are provided, they are ground truth for what appears in source "
                "documents. Never fabricate clinical facts."
            )

        degraded = False
        try:
            answer, confidence = await self.llm_answer_fn(
                prompt,
                prompt_id=prompt_id,
                db=self.db,
                user_id=self.user_id,
                case_id=self.case_id,
                system_message_override=system_message,
                on_token=self.on_answer_delta,
            )
        except Exception as e:
            logger.exception("Case agent LLM compose failed: %s", e)
            degraded = True
            has_summary = bool((self.ctx.narrative_markdown or "").strip())
            if has_summary:
                answer = (
                    "I could not finish generating a full reply right now. "
                    "The stored case summary is available for this version—please try again in a moment, "
                    "or ask a shorter follow-up question."
                )
            else:
                answer = (
                    "I could not generate a reply right now. Please try again in a moment."
                )
            confidence = 0.0

        extra_trace: List[Dict[str, Any]] = []
        provenance = "narrative_plus_evidence" if rag_context else "narrative_only"

        if (
            not degraded
            and not rag_context
            and should_retry_with_retrieval(
                self.intent,
                self.question,
                answer,
                ctx=self.ctx,
                did_initial_retrieval=self._used_initial_retrieval,
            )
        ):
            extra_trace.append(
                _step(
                    "retrieve_retry",
                    "Searching documents for more detail",
                    detail="The summary did not fully answer this question",
                )
            )
            try:
                plan = getattr(self, "_evidence_search_plan", None)
                if plan and plan.retrieval_required:
                    chunks = rag_retriever.retrieve_for_evidence_search(
                        db=self.db,
                        primary_query=self.question,
                        case_id=self.case_id,
                        user_id=self.user_id,
                        case_version_id=self.ctx.selected_version_id,
                        embedding_query=plan.embedding_query,
                        top_k=_CHAT_RETRIEVE_TOP_K,
                        use_adaptive=False,
                        merge_lexical_matches=True,
                        extra_lexical_terms=plan.lexical_terms,
                    )
                else:
                    chunks = rag_retriever.retrieve_for_query(
                        db=self.db,
                        query=self.question,
                        case_id=self.case_id,
                        user_id=self.user_id,
                        top_k=_CHAT_RETRIEVE_TOP_K,
                        use_adaptive=False,
                        case_version_id=self.ctx.selected_version_id,
                        merge_lexical_matches=True,
                    )
                rag_context = (
                    rag_retriever.build_context(chunks, max_tokens=_CHAT_MAX_CONTEXT_TOKENS)
                    if chunks
                    else None
                )
            except Exception as e:
                logger.warning("Case agent fallback RAG retrieve failed: %s", e)
                rag_context = None
            if rag_context:
                self._rag_context = rag_context
                variables = self._compose_prompt_variables(rag_context.formatted_context)
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
                    on_token=self.on_answer_delta,
                )
                provenance = "narrative_plus_evidence"

        blocks = dict(state.get("structured_blocks") or {})
        if self.intent == "contradictions" and self.ctx.contradictions_count:
            blocks["contradictions"] = {
                "count": self.ctx.contradictions_count,
                "preview": self.ctx.contradictions[:5] if self.ctx.contradictions else [],
            }
        self.ctx.register_artifact("tier1_completion")

        plan = getattr(self, "_evidence_search_plan", None)
        telemetry = {
            "intent": self.intent,
            "provenance": provenance,
            "initial_retrieval": self._used_initial_retrieval,
            "degraded_compose": degraded,
            "search_plan": plan.to_telemetry_dict() if plan else {},
        }

        return {
            "trace_steps": trace + extra_trace,
            "answer": answer,
            "confidence": confidence,
            "sources": _build_sources_from_rag(rag_context) if rag_context else state.get("sources"),
            "chunks_used": [c.chunk_id for c in rag_context.chunks] if rag_context else state.get("chunks_used"),
            "structured_blocks": blocks if blocks else state.get("structured_blocks"),
            "telemetry": telemetry,
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
        base_tel = dict(state.get("telemetry") or {})
        if "intent" not in base_tel and state.get("resolved_intent"):
            base_tel["intent"] = state.get("resolved_intent")
        return {
            "suggested_actions": sug,
            "context_summary": state.get("context_summary")
            or f"Intent={state.get('resolved_intent')}; v{getattr(self.ctx, 'selected_version_number', '?')}; complete.",
            "used_artifacts": used,
            "telemetry": base_tel,
        }


def _route_after_load(state: CaseAgentState) -> str:
    return "finalize" if state.get("short_circuit") else "classify"


def _route_after_classify(state: CaseAgentState) -> str:
    return "finalize" if state.get("short_circuit") else "narrative"


def _route_after_assess(state: CaseAgentState) -> str:
    if state.get("short_circuit"):
        return "compose"
    return "retrieve" if state.get("need_retrieval") else "compose"


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
        need_retrieval: bool
        telemetry: Dict[str, Any]

    workflow = StateGraph(FullState)
    workflow.add_node("load", runner.node_load_context)
    workflow.add_node("classify", runner.node_classify)
    workflow.add_node("narrative", runner.node_narrative)
    workflow.add_node("assess", runner.node_assess_evidence)
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
        {"finalize": "finalize", "narrative": "narrative"},
    )
    workflow.add_edge("narrative", "assess")
    workflow.add_conditional_edges(
        "assess",
        _route_after_assess,
        {"retrieve": "retrieve", "compose": "compose"},
    )
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
        telemetry=state.get("telemetry"),
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
    working_memory_text: Optional[str] = None,
) -> CaseAgentRunResult:
    runner = CaseAgentGraphRunner(
        db,
        case_id,
        user_id,
        question,
        history_text,
        include_dashboard_context,
        case_version_id,
        llm_answer_fn,
        working_memory_text=working_memory_text or "",
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
    working_memory_text: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream NDJSON-friendly events. Yields trace_delta then a final payload.
    """
    queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
    answer_buffer = ""
    last_flush_at = time.monotonic()

    async def _flush_answer_buffer(force: bool = False) -> None:
        nonlocal answer_buffer, last_flush_at
        if not answer_buffer:
            return
        elapsed = time.monotonic() - last_flush_at
        if not force and len(answer_buffer) < 48 and "\n" not in answer_buffer and elapsed < 0.06:
            return
        await queue.put({"type": "answer_delta", "delta": answer_buffer})
        answer_buffer = ""
        last_flush_at = time.monotonic()

    async def _on_answer_delta(delta: str) -> None:
        nonlocal answer_buffer
        if not delta:
            return
        answer_buffer += delta
        await _flush_answer_buffer()

    runner = CaseAgentGraphRunner(
        db,
        case_id,
        user_id,
        question,
        history_text,
        include_dashboard_context,
        case_version_id,
        llm_answer_fn,
        working_memory_text=working_memory_text or "",
        on_answer_delta=_on_answer_delta,
    )
    graph = build_case_agent_graph(runner)
    initial: CaseAgentState = {"trace_steps": []}

    async def _produce() -> None:
        prev_len = 0
        last_state: Dict[str, Any] = {}
        try:
            async for state in graph.astream(initial, stream_mode="values"):
                last_state = state
                steps = state.get("trace_steps") or []
                if len(steps) > prev_len:
                    await _flush_answer_buffer(force=True)
                    await queue.put({"type": "trace_delta", "steps": steps[prev_len:]})
                    prev_len = len(steps)

            await _flush_answer_buffer(force=True)
            final = _state_to_result(last_state, runner)
            await queue.put(
                {
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
                    "telemetry": final.telemetry,
                }
            )
        finally:
            await queue.put(None)

    producer = asyncio.create_task(_produce())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not producer.done():
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
