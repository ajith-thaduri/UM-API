"""
Tier-1 case agent: version-aware orchestration with optional RAG tool.
Uses precomputed Claude artifacts from DB only (no Tier-2 at chat time).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.case_agent_context_service import (
    CaseAgentContextBundle,
    derive_summary_guided_lexical_terms,
    extract_user_focus_terms_from_question,
    get_version_pair_for_compare,
)
from app.services.rag_retriever import RAGContext

LLMCaller = Callable[..., Awaitable[Tuple[str, float]]]


@dataclass
class EvidenceSearchPlan:
    """
    Summary-guided document search plan: keeps the Tier-2 summary authoritative while
    steering RAG using user wording + terms harvested from the summary.
    """

    question_type: str  # summary_answer | evidence_lookup | mixed
    answer_priority: str  # summary_first
    retrieval_required: bool
    retrieval_goal: str  # none | support_fact | locate_document | verify_excerpt
    retrieval_reason: str
    user_focus_terms: List[str]
    summary_guided_terms: List[str]
    embedding_query: str
    lexical_terms: List[str]

    def to_telemetry_dict(self) -> Dict[str, Any]:
        return {
            "question_type": self.question_type,
            "answer_priority": self.answer_priority,
            "retrieval_required": self.retrieval_required,
            "retrieval_goal": self.retrieval_goal,
            "user_focus_terms": self.user_focus_terms,
            "summary_guided_terms": self.summary_guided_terms,
        }


def _merge_unique_terms(*parts: List[str], max_n: int = 24) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for lst in parts:
        for t in lst or []:
            tt = (t or "").strip()
            if len(tt) < 2:
                continue
            k = tt.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(tt)
            if len(out) >= max_n:
                return out
    return out


def build_evidence_search_plan(
    intent: str,
    question: str,
    ctx: CaseAgentContextBundle,
    *,
    used_deterministic: bool = False,
) -> EvidenceSearchPlan:
    q = (question or "").strip()
    user_focus = extract_user_focus_terms_from_question(q)
    summary_guided = derive_summary_guided_lexical_terms(ctx, user_focus) if user_focus else []

    def make_plan(
        question_type: str,
        retrieve: bool,
        reason: str,
        goal: str,
    ) -> EvidenceSearchPlan:
        emb = q
        if retrieve:
            if summary_guided:
                emb = (
                    f"{q}\n\nTerms aligned with the stored case summary for document search: "
                    f"{', '.join(summary_guided[:14])}"
                )
            elif user_focus:
                emb = f"{q}\n\nFocus terms from your question: {', '.join(user_focus[:10])}"
        lex = _merge_unique_terms(user_focus, summary_guided, max_n=24)
        return EvidenceSearchPlan(
            question_type=question_type,
            answer_priority="summary_first",
            retrieval_required=retrieve,
            retrieval_goal=goal,
            retrieval_reason=reason,
            user_focus_terms=user_focus,
            summary_guided_terms=summary_guided,
            embedding_query=emb if retrieve else q,
            lexical_terms=lex,
        )

    if used_deterministic:
        return make_plan("summary_answer", False, "Answered without document search", "none")

    if intent in ("greeting", "assistant_identity", "version_count", "live_version"):
        return make_plan("summary_answer", False, "No document search needed", "none")

    if intent == "evidence_lookup":
        return make_plan("evidence_lookup", True, "Looking up pages in uploaded documents", "locate_document")

    if user_requests_document_evidence(q):
        return make_plan("evidence_lookup", True, "Looking up pages in uploaded documents", "locate_document")

    if intent in ("revision_diff", "compare_versions"):
        return make_plan("summary_answer", False, "Using version change summary first", "none")

    if intent == "contradictions":
        return make_plan("summary_answer", False, "Using case summary and structured facts first", "none")

    ql = q.lower()
    if intent == "timeline" and ("document" in ql or "page" in ql or "record" in ql):
        return make_plan("mixed", True, "Looking up timeline details in documents", "locate_document")

    if intent == "case_summary":
        return make_plan("summary_answer", False, "Using stored case summary", "none")

    if intent == "timeline":
        return make_plan("summary_answer", False, "Using case context for timeline", "none")

    if intent == "general_case_qa" and not (ctx.narrative_markdown or "").strip():
        return make_plan("mixed", True, "No stored summary yet; searching documents", "support_fact")

    if intent == "general_case_qa":
        return make_plan("summary_answer", False, "Using case summary first", "none")

    return make_plan("summary_answer", False, "Using case summary first", "none")


def format_search_plan_for_prompt(plan: Optional[EvidenceSearchPlan]) -> str:
    """Inject into case_agent_answer so the model follows the same tool workflow as the graph."""
    if plan is None:
        return (
            "=== DOCUMENT_SEARCH_PLAN ===\n"
            "(No document search plan for this turn.)"
        )
    if not plan.retrieval_required:
        return (
            "=== DOCUMENT_SEARCH_PLAN ===\n"
            "No uploaded-document search is required for this question.\n"
            "Answer from the stored case summary and structured facts; do not invent document page numbers."
        )
    return (
        "=== DOCUMENT_SEARCH_PLAN (tool workflow for this turn) ===\n"
        f"- Question type: {plan.question_type}\n"
        f"- Retrieval goal: {plan.retrieval_goal}\n"
        f"- User focus terms: {', '.join(plan.user_focus_terms) or '(none extracted)'}\n"
        f"- Summary-aligned search terms: {', '.join(plan.summary_guided_terms) or '(none)'}\n"
        "- The stored case summary remains authoritative for clinical facts.\n"
        "- For file names, document numbers, or page numbers: cite them **only** if they appear in the "
        "supporting document excerpts below.\n"
        "- If excerpts do not contain a clear location, say the summary supports the topic but a matching "
        "page/document was not located in the retrieved excerpts.\n"
    )


@dataclass
class CaseAgentRunResult:
    answer: str
    sources: List[Dict[str, Any]]
    chunks_used: List[str]
    confidence: float
    suggested_actions: List[str] = field(default_factory=list)
    trace_steps: List[Dict[str, Any]] = field(default_factory=list)
    context_summary: Optional[str] = None
    active_version_summary: Optional[Dict[str, Any]] = None
    used_artifacts: List[str] = field(default_factory=list)
    structured_blocks: Optional[Dict[str, Any]] = None
    resolved_intent: Optional[str] = None
    # False for trivial intents (greeting, version_count, live_version) —
    # the frontend uses this to hide the execution-steps panel.
    show_trace: bool = True
    telemetry: Optional[Dict[str, Any]] = None


def _step(sid: str, label: str, status: str = "done") -> Dict[str, Any]:
    return {"id": sid, "label": label, "status": status}


_GREETING_RE = re.compile(
    r"^(hi+|hello+|hey+|yo+|sup|hiya|howdy|greetings|"
    r"good\s+(morning|afternoon|evening|day)|"
    r"what'?s\s+up|how\s+are\s+you|how'?s\s+it\s+going|"
    r"tell\s+me\s+about\s+(yourself|this\s+chat)|"
    r"start|begin|let'?s\s+(start|begin|go))[!?.]*$",
    re.IGNORECASE,
)

# User is asking for location in uploads (pages/files) — must run RAG before compose, and may retry if skipped.
_DOCUMENT_EVIDENCE_QUERY_RE = re.compile(
    r"\bpage\b|\bpages\b|"
    r"\bwhich document\b|\bwhat document\b|\bwhich of the documents?\b|"
    r"\bin which (?:the )?(?:document|file)\b|\bwhich file\b|\bwhat file\b|\bin which file\b|"
    r"\bwhere in the\b|\bshow me (?:the )?source\b|\bcite\b|\bevidence\b|\bexcerpt\b|\bscan\b|\bembedding\b|"
    r"\brecord\b|\bchart\b|"
    r"\bwhere\b[\s\S]{0,160}\bdocumented\b|"
    r"\bdocumented in (?:which|what|the)\s+(?:document|file|record|chart)\b",
    re.IGNORECASE,
)


def classify_intent(question: str) -> str:
    q = question.lower().strip()

    if _GREETING_RE.match(q):
        return "greeting"
    if re.search(
        r"\bwho\s+(are|r|re)\s+you\b|\bwho\s+r\s+u\b|\bwhat'?s\s+your\s+name\b",
        q,
    ):
        return "assistant_identity"
    if re.search(
        r"\bwhat\s+can\s+you\s+do\b|\bwhat\s+do\s+you\s+do\b|\bhow\s+can\s+you\s+help\b|\bhow\s+can\s+i\s+use\b|\bhelp\b|\btell\s+me\s+what\s+you\s+do\b",
        q,
    ):
        return "assistant_identity"
    if re.search(r"\bhow many versions\b|\bnumber of versions\b|\bversions does this case\b", q):
        return "version_count"
    if re.search(r"\blive version\b|\bcurrent live\b|\bproduction version\b|\bwhich version is live\b", q):
        return "live_version"
    if re.search(
        r"\bboth versions\b|\beach version\b|\ball versions\b|\bat a time\b|\bcompare versions\b",
        q,
    ):
        return "compare_versions"
    if re.search(r"\bcontradict|\binconsisten|\bconflict", q):
        return "contradictions"
    if re.search(
        r"\bwhat changed\b|\bdiff\b|\bdifference\b|\bchanged from\b|\bbetween\s+v?\d+\s+and\s+v?\d+|\bv\d+\s+and\s+v\d+|\bversion\s+\d+\s+.*\bversion\s+\d+",
        q,
    ):
        return "revision_diff"
    if re.search(r"\btimeline\b|\bchronolog|\bwhen did\b|\bsequence of events\b", q):
        return "timeline"
    if re.search(r"\bsummarize the case\b|\bhigh.level overview\b|\bexecutive summary\b", q):
        return "case_summary"
    if _DOCUMENT_EVIDENCE_QUERY_RE.search(q):
        return "evidence_lookup"

    return "general_case_qa"


def _parse_version_compare(question: str) -> Optional[Tuple[int, int]]:
    ql = question.lower()
    m = re.search(r"v?(\d+)\s+and\s+v?(\d+)", ql)
    if m:
        return int(m.group(1)), int(m.group(2))
    m2 = re.search(r"between\s+v?(\d+)\s+and\s+v?(\d+)", ql)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    m3 = re.search(r"version\s+(\d+)\s*(?:-|–|to|through|and)\s*version\s+(\d+)", ql)
    if m3:
        return int(m3.group(1)), int(m3.group(2))
    m4 = re.search(r"\bv(\d+)\s*(?:-|–|to)\s*v(\d+)", ql)
    if m4:
        return int(m4.group(1)), int(m4.group(2))
    return None


def resolve_compare_versions(
    db: Session,
    case_id: str,
    user_id: str,
    question: str,
    ctx: CaseAgentContextBundle,
    intent: Optional[str] = None,
) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Resolve (lower_version_row, higher_version_row) for compare / revision questions.
    Uses explicit vN patterns, 'both versions', or base_version vs selected.
    """
    from app.repositories.case_version_repository import case_version_repository

    pair = _parse_version_compare(question)
    if pair:
        lo, hi = get_version_pair_for_compare(db, case_id, user_id, pair[0], pair[1])
        if lo and hi:
            return lo, hi

    ql = question.lower()
    if re.search(r"\bboth versions\b|\beach version\b|\ball versions\b|\bat a time\b|\bcompare versions\b", ql):
        versions = case_version_repository.list_for_case(db, case_id, user_id)
        if len(versions) >= 2:
            return versions[0], versions[-1]

    eff_intent = intent or classify_intent(question)
    if eff_intent in ("revision_diff", "compare_versions") or re.search(
        r"\bwhat changed\b|\bdiff\b|\bdifference\b|\bchanged from\b|\brevision\b|\bcompare\b",
        ql,
    ):
        if ctx.base_version_id:
            base = case_version_repository.get_by_id_for_user(db, ctx.base_version_id, user_id)
            sel = case_version_repository.get_by_id_for_user(db, ctx.selected_version_id, user_id)
            if base and sel and base.id != sel.id:
                if base.version_number <= sel.version_number:
                    return base, sel
                return sel, base
        if ctx.version_count == 2:
            versions = case_version_repository.list_for_case(db, case_id, user_id)
            if len(versions) >= 2:
                return versions[0], versions[-1]

    return None, None


def build_compare_enrichment(
    db: Session,
    case_id: str,
    user_id: str,
    question: str,
    ctx: CaseAgentContextBundle,
    intent: Optional[str] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Build extra prompt text + structured compare card from resolved version pair."""
    from app.repositories.extraction_repository import extraction_repository

    lo, hi = resolve_compare_versions(db, case_id, user_id, question, ctx, intent=intent)
    if not lo or not hi:
        return "", None

    extra_parts: List[str] = []
    extra_parts.append(f"\n=== COMPARE v{lo.version_number} (lower) → v{hi.version_number} (higher) ===\n")
    extra_parts.append(
        "Answer using the higher version's pipeline artifacts first (revision_impact_report, change_summary). "
        "Then contrast with the lower version's summaries only if needed for 'both versions' questions.\n"
    )

    if hi.revision_impact_report:
        extra_parts.append("revision_impact_report (v{}):\n".format(hi.version_number))
        extra_parts.append(json.dumps(hi.revision_impact_report, default=str, ensure_ascii=False)[:10000])
        ctx.register_artifact("revision_impact_report")
    elif hi.change_summary:
        extra_parts.append(f"change_summary (v{hi.version_number}):\n")
        extra_parts.append((hi.change_summary or "")[:8000])
        ctx.register_artifact("change_summary")

    ex_lo = extraction_repository.get_by_case_id_and_version(db, case_id, lo.id, user_id=user_id)
    ex_hi = extraction_repository.get_by_case_id_and_version(db, case_id, hi.id, user_id=user_id)
    if ex_lo and (ex_lo.summary or ex_lo.executive_summary):
        extra_parts.append(f"\n=== v{lo.version_number} extraction summary (excerpt) ===\n")
        extra_parts.append((ex_lo.summary or ex_lo.executive_summary or "")[:3500])
        ctx.register_artifact("extraction_summary")
    if ex_hi and (ex_hi.summary or ex_hi.executive_summary):
        extra_parts.append(f"\n=== v{hi.version_number} extraction summary (excerpt) ===\n")
        extra_parts.append((ex_hi.summary or ex_hi.executive_summary or "")[:3500])
        ctx.register_artifact("extraction_summary")

    block = {
        "compare_versions": {
            "from_version": lo.version_number,
            "to_version": hi.version_number,
            "has_revision_impact": bool(hi.revision_impact_report or hi.change_summary),
        }
    }
    return "\n".join(extra_parts), block


def _greeting_response(ctx: CaseAgentContextBundle, question: str = "") -> str:
    """Professional greeting with patient name; 'Hey' still gets a Hello-style reply."""
    _ = question  # reserved for future personalization by exact phrase
    name = (ctx.patient_name or "").strip()
    junk = {"unknown", "patient", "n/a", "none", "tbd", ""}
    if name and name.lower() not in junk:
        lines: List[str] = [
            f"Hello! I'm ready to help with your case regarding **{name}**.",
        ]
    else:
        lines = ["Hello! I'm ready to help with this case."]

    # One context line — version + notable flags (use **bold** only; UI markdown does not render *italic*)
    ctx_parts: List[str] = []
    if ctx.version_count > 1:
        ctx_parts.append(
            f"v{ctx.selected_version_number} of {ctx.version_count} versions"
        )
    if ctx.revision_impact_report or ctx.change_summary:
        ctx_parts.append("revision data available")
    if ctx.contradictions_count:
        noun = "contradiction" if ctx.contradictions_count == 1 else "contradictions"
        ctx_parts.append(f"{ctx.contradictions_count} {noun} flagged")
    if ctx.review_flags:
        ctx_parts.append("review flags present")

    if ctx_parts:
        lines.append("**" + " · ".join(ctx_parts) + "**")

    lines.append("What would you like to know?")
    return "\n\n".join(lines)


def context_aware_suggestions(
    intent: str, ctx: CaseAgentContextBundle, answer: str = "", question: str = ""
) -> List[str]:
    """
    Return up to 3 context-specific follow-up suggestions.
    For structured intents use case artifacts; fall back to keyword scanning.
    """
    if intent == "greeting":
        out: List[str] = []
        # Highest-value actions first, based on what's actually in the case
        has_revision = bool(ctx.revision_impact_report or ctx.change_summary)
        if has_revision and ctx.version_count > 1:
            out.append("What changed in this revision?")
        if ctx.contradictions_count:
            noun = "contradiction" if ctx.contradictions_count == 1 else "contradictions"
            out.append(f"Walk me through the {ctx.contradictions_count} {noun}")
        if ctx.review_flags:
            out.append("What are the review flags?")
        # Always-useful fallbacks
        fallbacks = [
            "Summarize this case",
            "What are the key diagnoses?",
            "What medications is the patient on?",
        ]
        for fb in fallbacks:
            if len(out) >= 3:
                break
            out.append(fb)
        return out[:3]

    if intent == "assistant_identity":
        out: List[str] = []
        out.append("Summarize this case")
        if ctx.contradictions_count:
            noun = "contradiction" if ctx.contradictions_count == 1 else "contradictions"
            out.append(f"Review the {ctx.contradictions_count} {noun}")
        if ctx.version_count > 1:
            out.append("What changed between versions?")
        return out[:3]

    # Non-greeting: keyword-driven as before
    return _extract_suggested_actions(answer, question)


def _try_deterministic_answer(
    question: str, ctx: CaseAgentContextBundle, intent: str
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    blocks: Dict[str, Any] = {}

    if intent == "greeting":
        return _greeting_response(ctx, question), None

    if intent == "assistant_identity":
        ans = (
            "I'm your utilization management (UM) case assistant. "
            "I can answer questions grounded in the case you selected (diagnoses, medications, "
            "timeline, contradictions, and version comparisons), and I can point out where the "
            "information is documented."
        )
        return ans, None

    if intent == "version_count":
        blocks["version_overview"] = {
            "total_versions": ctx.version_count,
            "selected_version_number": ctx.selected_version_number,
            "live_version_number": ctx.live_version_number,
            "chatting_on_live": ctx.is_on_live,
        }
        ans = (
            f"This case has **{ctx.version_count}** processing version(s). "
            f"You are asking from **v{ctx.selected_version_number}**"
        )
        if ctx.live_version_number:
            ans += f"; the **live** version is **v{ctx.live_version_number}**"
        ans += "."
        if not ctx.is_on_live and ctx.live_version_number:
            ans += " (You are not on the live version for this chat.)"
        return ans, blocks

    if intent == "live_version":
        blocks["live_version"] = {
            "live_version_number": ctx.live_version_number,
            "live_version_id": ctx.live_version_id,
            "selected_version_number": ctx.selected_version_number,
        }
        if ctx.live_version_number:
            return (
                f"The **live (production) version** for this case is **v{ctx.live_version_number}**.",
                blocks,
            )
        return ("No **live** version is currently set for this case.", blocks)

    return None, None


def user_requests_document_evidence(question: str) -> bool:
    """User explicitly wants pages, documents, or source locations."""
    return bool(_DOCUMENT_EVIDENCE_QUERY_RE.search(question or ""))


def assess_should_retrieve_before_compose(
    intent: str, question: str, ctx: CaseAgentContextBundle, used_deterministic: bool
) -> Tuple[bool, str]:
    """
    Narrative-first: retrieve chunks only when needed for grounding / user asked for location.
    Delegates to build_evidence_search_plan so routing and RAG query shaping stay aligned.
    """
    plan = build_evidence_search_plan(intent, question, ctx, used_deterministic=used_deterministic)
    return plan.retrieval_required, plan.retrieval_reason


def retrieval_policy(intent: str, question: str, used_deterministic: bool) -> Tuple[bool, str]:
    """Legacy wrapper; prefer assess_should_retrieve_before_compose with ctx when available."""
    if used_deterministic:
        return False, "Deterministic answer; no retrieval"
    if intent == "greeting":
        return False, "Greeting can be answered without retrieval"
    if intent == "assistant_identity":
        return False, "Assistant identity/help can be answered without retrieval"
    if intent == "evidence_lookup":
        return True, "Page/source lookup requires document chunks"
    if intent in ("version_count", "live_version"):
        return False, "Version metadata is sufficient"
    if intent in ("revision_diff", "compare_versions"):
        return False, "Compare uses version artifacts first"
    if intent == "contradictions":
        return False, "Contradictions use summary and structured facts first"
    q = question.lower()
    if intent == "timeline" and ("document" in q or "page" in q or "record" in q):
        return True, "Timeline question references documents/pages"
    if intent == "case_summary":
        return False, "Case summary should come from stored narrative"
    if intent == "timeline":
        return False, "Start with case context for timeline"
    if intent == "general_case_qa":
        return False, "Using case summary first; document search only if needed"
    return False, "Using case summary first; document search only if needed"


def should_retry_with_retrieval(
    intent: str,
    question: str,
    answer: str,
    ctx: Optional[CaseAgentContextBundle] = None,
    *,
    did_initial_retrieval: bool = True,
) -> bool:
    """
    After a narrative-first answer, decide whether to fall back to document search.
    Conservative: avoid retrieval when user did not ask for sources and answer is sufficient.
    If the user asked for document/page evidence but we skipped the retrieve node, always retry with RAG.
    """
    if intent in {
        "greeting",
        "assistant_identity",
        "version_count",
        "live_version",
        "case_summary",
        "evidence_lookup",
    }:
        return False
    if intent in ("revision_diff", "compare_versions") and not user_requests_document_evidence(question):
        return False

    if user_requests_document_evidence(question):
        if not did_initial_retrieval:
            return True
        return False

    a = answer.lower()
    insufficiency_markers = (
        "not documented",
        "not available",
        "not mentioned",
        "not stated",
        "not found in the case context",
        "not found in the summary",
        "not in the summary",
        "insufficient information",
        "unable to determine from the case context",
        "unable to determine from the summary",
        "unclear from the case context",
        "unclear from the summary",
        "i don't have",
        "cannot find",
    )
    if any(marker in a for marker in insufficiency_markers):
        return True
    if ctx and intent == "general_case_qa" and not (ctx.narrative_markdown or "").strip():
        return True
    return False


def _should_retrieve_chunks(intent: str, question: str, used_deterministic: bool) -> bool:
    return retrieval_policy(intent, question, used_deterministic)[0]


def _build_sources_from_rag(rag_context: Optional[RAGContext]) -> List[Dict[str, Any]]:
    if not rag_context:
        return []
    out = []
    for chunk in rag_context.chunks:
        out.append(
            {
                "chunk_id": chunk.chunk_id,
                "vector_id": chunk.vector_id,
                "file_id": chunk.file_id,
                "page_number": chunk.page_number,
                "section_type": chunk.section_type.value,
                "score": chunk.score,
                "text_preview": chunk.chunk_text[:200] + "..."
                if len(chunk.chunk_text) > 200
                else chunk.chunk_text,
            }
        )
    return out


def _extract_suggested_actions(answer: str, question: str) -> List[str]:
    suggestions: List[str] = []
    answer_lower = answer.lower()
    question_lower = question.lower()
    if "page" in answer_lower:
        suggestions.append("View source document")
    if any(kw in question_lower for kw in ("when", "date", "timeline", "history")):
        suggestions.append("Review clinical timeline")
    if any(kw in question_lower for kw in ("medication", "drug", "prescription")):
        suggestions.append("Review medication list")
    return suggestions[:3]


async def run_case_agent_turn(
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
    """Tier-1 case agent via LangGraph (tools as explicit nodes)."""
    from app.services.case_agent_graph import invoke_case_agent_graph

    return await invoke_case_agent_graph(
        db=db,
        case_id=case_id,
        user_id=user_id,
        question=question,
        history_text=history_text,
        include_dashboard_context=include_dashboard_context,
        case_version_id=case_version_id,
        llm_answer_fn=llm_answer_fn,
        working_memory_text=working_memory_text,
    )
