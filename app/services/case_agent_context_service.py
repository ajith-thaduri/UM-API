"""
Assemble version-aware case context for the Tier-1 case agent from DB rows only.
Claude/Tier-2 outputs are read as structured artifacts (JSON/text), not invoked at runtime.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_version import CaseVersion, CaseVersionStatus
from app.repositories.case_version_repository import case_version_repository
from app.repositories.extraction_repository import extraction_repository

logger = logging.getLogger(__name__)

# Primary narrative for Ask AI: Tier-2 stored case summary (markdown body)
MAX_NARRATIVE_MARKDOWN_CHARS = 18000

# Stopwords for generic term extraction (summary-guided lexical hints; not clinical-specific).
_LEX_STOPWORDS = frozenset(
    """
    the a an is are was were be been being to of in for on at by with from as or and but if then
    this that these those it its they them their we you he she his her has have had do does did not
    no yes so than then into out up down all any some each both few more most other such only same
    can could should would will may might must shall about over after before again further once here
    there when where why how what which who whom whose during through while within without between
    under again until against among per via also very just than too very
    patient case version summary document page file record chart data information please tell me
    """.split()
)


def extract_user_focus_terms_from_question(question: str, max_terms: int = 8) -> List[str]:
    """
    Pull likely search tokens from the user question (quoted phrases + alphanumeric tokens).
    Generic — not disease-specific.
    """
    q = question or ""
    out: List[str] = []
    seen: set[str] = set()
    for phrase in re.findall(r'"([^"]+)"', q) + re.findall(r"'([^']+)'", q):
        p = phrase.strip()
        if len(p) >= 2 and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", q):
        w = raw.strip("-")
        wl = w.lower()
        if wl in _LEX_STOPWORDS or wl in seen or len(wl) < 3:
            continue
        seen.add(wl)
        out.append(w)
        if len(out) >= max_terms:
            break
    return out[:max_terms]


def derive_summary_guided_lexical_terms(
    ctx: "CaseAgentContextBundle",
    user_terms: List[str],
    *,
    max_output: int = 16,
    summary_sample_chars: int = 12000,
) -> List[str]:
    """
    When user terms appear in the authoritative summary, harvest nearby tokens from that snippet
    to broaden document search (OCR may use different wording than the user).
    """
    narrative = (ctx.narrative_markdown or "")[:summary_sample_chars]
    narrative_lower = narrative.lower()
    out: List[str] = []
    seen: set[str] = set()

    for ut in user_terms or []:
        ul = (ut or "").lower().strip()
        if len(ul) < 2 or ul not in narrative_lower:
            continue
        idx = narrative_lower.find(ul)
        start = max(0, idx - 140)
        end = min(len(narrative), idx + len(ut) + 140)
        frag = narrative[start:end]
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", frag):
            w = raw.strip("-")
            wl = w.lower()
            if wl in _LEX_STOPWORDS or wl in seen or len(wl) < 3:
                continue
            seen.add(wl)
            out.append(w)
            if len(out) >= max_output:
                return out[:max_output]
    return out[:max_output]


def extract_tier2_summary_markdown(stored: Any) -> str:
    """
    Normalize ClinicalExtraction.summary into plain markdown/text for prompts.
    Handles JSON strings/objects with markdown/body fields and raw text.
    """
    if stored is None:
        return ""
    if isinstance(stored, dict):
        body = stored.get("markdown") or stored.get("body") or stored.get("summary") or stored.get("text")
        if body is not None:
            return str(body).strip()[:MAX_NARRATIVE_MARKDOWN_CHARS]
        try:
            return json.dumps(stored, default=str, ensure_ascii=False)[:MAX_NARRATIVE_MARKDOWN_CHARS]
        except Exception:
            return str(stored)[:MAX_NARRATIVE_MARKDOWN_CHARS]
    s = str(stored).strip()
    if not s:
        return ""
    if s.startswith("{") or s.startswith("["):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                inner = obj.get("markdown") or obj.get("body") or obj.get("summary") or obj.get("text")
                if inner is not None:
                    return str(inner).strip()[:MAX_NARRATIVE_MARKDOWN_CHARS]
                return json.dumps(obj, default=str, ensure_ascii=False)[:MAX_NARRATIVE_MARKDOWN_CHARS]
        except json.JSONDecodeError:
            pass
    return s[:MAX_NARRATIVE_MARKDOWN_CHARS]


def _json_preview(obj: Any, max_chars: int = 12000) -> str:
    if obj is None:
        return ""
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False, indent=2)
    except Exception:
        s = str(obj)
    if len(s) > max_chars:
        return s[: max_chars - 20] + "\n… [truncated]"
    return s


@dataclass
class CaseAgentContextBundle:
    """Everything the agent needs from repositories (no LLM)."""

    case_id: str
    user_id: str
    selected_version_id: str
    selected_version_number: int
    selected_status: str
    live_version_id: Optional[str]
    live_version_number: Optional[int]
    base_version_id: Optional[str]
    base_version_number: Optional[int]
    version_count: int
    is_on_live: bool
    change_summary: Optional[str]
    revision_impact_report: Any
    confidence_summary: Any
    review_flags: Any
    version_processing_metadata: Any
    extraction_summary: Optional[str]
    executive_summary: Optional[str]
    contradictions: List[Any]
    contradictions_count: int
    dashboard_extraction_bullets: str
    lineage_text: str
    # Normalized markdown from Tier-2 stored case summary (ClinicalExtraction.summary)
    narrative_markdown: str = ""
    patient_name: str = ""
    used_artifact_keys: List[str] = field(default_factory=list)

    def register_artifact(self, key: str) -> None:
        if key and key not in self.used_artifact_keys:
            self.used_artifact_keys.append(key)

    def narrative_context(self) -> str:
        """Authoritative single-version narrative channel (Tier-2 summary)."""
        parts: List[str] = [
            "=== AUTHORITATIVE_CASE_SUMMARY (Tier-2 stored narrative; primary story for this version) ===",
        ]
        if self.narrative_markdown.strip():
            parts.append(self.narrative_markdown.strip())
            self.register_artifact("tier2_case_summary")
        else:
            parts.append(
                "(No stored case summary is available for this version yet. "
                "Use structured clinical facts and document excerpts when provided.)"
            )
        return "\n".join(parts)

    def version_context(self) -> str:
        """Version metadata and lineage only (no full narrative)."""
        parts: List[str] = ["=== VERSION_AND_LINEAGE ==="]
        parts.append(f"Total versions for this case: {self.version_count}")
        parts.append(
            f"Selected chat version: v{self.selected_version_number} "
            f"(id={self.selected_version_id}, status={self.selected_status})"
        )
        if self.live_version_number:
            parts.append(f"Live (production) version: v{self.live_version_number} (id={self.live_version_id})")
        else:
            parts.append("Live version: not set")
        parts.append(f"User is chatting on live version: {self.is_on_live}")
        if self.base_version_number:
            parts.append(f"Selected version base (parent): v{self.base_version_number} (id={self.base_version_id})")
        parts.append(self.lineage_text)
        self.register_artifact("version_metadata")
        return "\n".join(parts)

    def review_artifacts_context(self) -> str:
        """Version pipeline / reviewer artifacts (deltas, flags, confidence)."""
        parts: List[str] = ["=== REVIEW_ARTIFACTS (version changes and reviewer signals) ==="]
        if self.change_summary:
            parts.append("Change summary (short):\n" + self.change_summary[:8000])
            self.register_artifact("change_summary")
        if self.revision_impact_report:
            parts.append("Revision impact (structured; prefer for what changed between versions):\n")
            parts.append(_json_preview(self.revision_impact_report))
            self.register_artifact("revision_impact_report")
        if self.confidence_summary:
            parts.append("Confidence summary:\n" + _json_preview(self.confidence_summary))
            self.register_artifact("confidence_summary")
        if self.review_flags:
            parts.append("Review flags:\n" + _json_preview(self.review_flags))
            self.register_artifact("review_flags")
        if self.version_processing_metadata:
            parts.append("Version processing metadata (compact):\n")
            parts.append(_json_preview(self.version_processing_metadata, max_chars=4000))
            self.register_artifact("version_processing_metadata")
        if len(parts) == 1:
            parts.append("(No additional review artifacts for this version.)")
        return "\n".join(parts)

    def extraction_facts_context(self) -> str:
        """
        Supporting structured facts: contradictions list, bullets, executive summary.
        Does not repeat the full Tier-2 narrative body (see narrative_markdown).
        """
        parts: List[str] = ["=== STRUCTURED_CLINICAL_FACTS (supporting; align with authoritative summary) ==="]
        if self.executive_summary:
            parts.append("Executive summary (short):\n" + str(self.executive_summary)[:4000])
            self.register_artifact("executive_summary")
        parts.append("\n=== CONTRADICTIONS (from extraction; support narrative — do not invent new ones) ===")
        parts.append(f"Count: {self.contradictions_count}")
        if self.contradictions:
            parts.append(_json_preview(self.contradictions[:50], max_chars=6000))
            self.register_artifact("contradictions")
        parts.append("\n=== CLINICAL_FACTS_BULLETS ===")
        parts.append(self.dashboard_extraction_bullets)
        return "\n".join(parts)

    def build_narrative_first_context(
        self,
        *,
        include_dashboard_context: bool,
        revision_compare_extra: str = "",
        search_plan_context: str = "",
    ) -> Dict[str, str]:
        """
        Variables for case_agent_answer narrative-first template.
        Keys must match prompt placeholders in DB migration.
        """
        plan_block = (search_plan_context or "").strip() or (
            "=== DOCUMENT_SEARCH_PLAN ===\n"
            "(No document search plan for this turn.)"
        )
        if not include_dashboard_context:
            return {
                "authoritative_case_summary": self.narrative_context(),
                "version_and_lineage": (
                    "=== VERSION_AND_LINEAGE (minimal) ===\n"
                    f"Selected v{self.selected_version_number}; live v{self.live_version_number}; "
                    f"versions: {self.version_count}\n"
                ),
                "review_artifacts": "(Dashboard context omitted by request.)",
                "structured_clinical_facts": "(Dashboard context omitted by request.)",
                "revision_compare_extra": revision_compare_extra or "",
                "search_plan_context": plan_block,
            }
        return {
            "authoritative_case_summary": self.narrative_context(),
            "version_and_lineage": self.version_context(),
            "review_artifacts": self.review_artifacts_context(),
            "structured_clinical_facts": self.extraction_facts_context(),
            "revision_compare_extra": revision_compare_extra or "",
            "search_plan_context": plan_block,
        }

    def to_prompt_sections(self) -> str:
        """Backward-compatible single blob: narrative first, then version, review, facts."""
        parts: List[str] = [
            self.narrative_context(),
            self.version_context(),
            self.review_artifacts_context(),
            self.extraction_facts_context(),
        ]
        return "\n\n".join(parts)


def build_case_agent_context(
    db: Session,
    case_id: str,
    user_id: str,
    case_version_id: Optional[str],
) -> Optional[CaseAgentContextBundle]:
    """
    Load case, version list, selected version row, and extraction for the selected version.
    Returns None if case/version not found for user.
    """
    case = db.query(Case).filter(Case.id == case_id, Case.user_id == user_id).first()
    if not case:
        return None

    versions = case_version_repository.list_for_case(db, case_id, user_id)
    version_count = len(versions)
    vid = case_version_id or case.live_version_id
    if not vid and versions:
        vid = versions[0].id

    selected: Optional[CaseVersion] = None
    for v in versions:
        if v.id == vid:
            selected = v
            break
    if not selected and vid:
        selected = case_version_repository.get_by_id_for_user(db, vid, user_id)
    if not selected:
        return None

    live = case_version_repository.get_live_for_case(db, case_id)
    live_vid = live.id if live else None
    live_num = live.version_number if live else None

    base_num = None
    base_id = selected.base_version_id
    if base_id:
        base_row = next((x for x in versions if x.id == base_id), None)
        if base_row:
            base_num = base_row.version_number

    extraction = extraction_repository.get_by_case_id_and_version(
        db, case_id, selected.id, user_id=user_id
    )

    contradictions: List[Any] = []
    if extraction and extraction.contradictions:
        contradictions = extraction.contradictions if isinstance(extraction.contradictions, list) else []

    bullets = _dashboard_bullets_from_extraction(extraction)
    narrative_md = extract_tier2_summary_markdown(extraction.summary if extraction else None)

    lineage_parts = []
    for v in versions:
        tag = "LIVE" if live and v.id == live.id else "draft" if v.status != CaseVersionStatus.READY else "ready"
        lineage_parts.append(f"  - v{v.version_number} id={v.id} status={v.status.value} [{tag}]")
    lineage_text = "Version lineage:\n" + "\n".join(lineage_parts)

    patient_nm = (case.patient_name or "").strip()

    return CaseAgentContextBundle(
        case_id=case_id,
        user_id=user_id,
        selected_version_id=selected.id,
        selected_version_number=selected.version_number,
        selected_status=selected.status.value,
        live_version_id=live_vid,
        live_version_number=live_num,
        base_version_id=base_id,
        base_version_number=base_num,
        version_count=version_count,
        is_on_live=bool(live_vid and selected.id == live_vid),
        change_summary=selected.change_summary,
        revision_impact_report=selected.revision_impact_report,
        confidence_summary=selected.confidence_summary,
        review_flags=selected.review_flags,
        version_processing_metadata=selected.version_processing_metadata,
        extraction_summary=extraction.summary if extraction else None,
        executive_summary=extraction.executive_summary if extraction else None,
        contradictions=contradictions,
        contradictions_count=len(contradictions),
        dashboard_extraction_bullets=bullets,
        lineage_text=lineage_text,
        narrative_markdown=narrative_md,
        patient_name=patient_nm,
        used_artifact_keys=[],
    )


def _dashboard_bullets_from_extraction(extraction) -> str:
    if not extraction:
        return "No clinical extraction row for this version."
    extracted = extraction.extracted_data or {}
    parts: List[str] = []

    diagnoses = extracted.get("diagnoses") or []
    dx_list: List[str] = []
    for dx in diagnoses:
        if isinstance(dx, str):
            dx_list.append(dx)
        elif isinstance(dx, dict):
            dx_list.append(str(dx.get("name") or dx.get("diagnosis") or ""))
    if dx_list:
        parts.append(f"DIAGNOSES: {', '.join(dx_list[:20])}")

    meds = extracted.get("medications") or []
    parts.append(f"MEDICATIONS: {len(meds)} documented")

    labs = extracted.get("labs") or []
    abnormal = len([l for l in labs if isinstance(l, dict) and l.get("abnormal")])
    parts.append(f"LABS: {len(labs)} results ({abnormal} flagged abnormal)")

    procs = extracted.get("procedures") or []
    parts.append(f"PROCEDURES: {len(procs)} documented")

    timeline = extraction.timeline or []
    parts.append(f"TIMELINE events: {len(timeline)}")

    return "\n".join(parts) if parts else "Extraction present but sparse structured fields."


def get_version_pair_for_compare(
    db: Session, case_id: str, user_id: str, a: int, b: int
) -> tuple[Optional[CaseVersion], Optional[CaseVersion]]:
    """Return (lower_v, higher_v) by version_number for two version numbers."""
    va = case_version_repository.get_by_case_and_number(db, case_id, min(a, b))
    vb = case_version_repository.get_by_case_and_number(db, case_id, max(a, b))
    if not va or not vb:
        return None, None
    if va.user_id != user_id or vb.user_id != user_id:
        return None, None
    return va, vb
