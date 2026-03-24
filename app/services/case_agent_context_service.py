"""
Assemble version-aware case context for the Tier-1 case agent from DB rows only.
Claude/Tier-2 outputs are read as structured artifacts (JSON/text), not invoked at runtime.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_version import CaseVersion, CaseVersionStatus
from app.repositories.case_version_repository import case_version_repository
from app.repositories.extraction_repository import extraction_repository

logger = logging.getLogger(__name__)


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
    used_artifact_keys: List[str] = field(default_factory=list)

    def register_artifact(self, key: str) -> None:
        if key and key not in self.used_artifact_keys:
            self.used_artifact_keys.append(key)

    def to_prompt_sections(self) -> str:
        """Compact text blocks for the Tier-1 prompt."""
        parts: List[str] = []
        parts.append("=== VERSION_METADATA (authoritative) ===")
        parts.append(f"Total versions for this case: {self.version_count}")
        parts.append(f"Selected chat version: v{self.selected_version_number} (id={self.selected_version_id}, status={self.selected_status})")
        if self.live_version_number:
            parts.append(f"Live (production) version: v{self.live_version_number} (id={self.live_version_id})")
        else:
            parts.append("Live version: not set")
        parts.append(f"User is chatting on live version: {self.is_on_live}")
        if self.base_version_number:
            parts.append(f"Selected version base (parent): v{self.base_version_number} (id={self.base_version_id})")
        parts.append(self.lineage_text)

        if self.change_summary:
            parts.append("\n=== change_summary (Claude/version pipeline) ===")
            parts.append(self.change_summary[:8000])
            self.register_artifact("change_summary")

        if self.revision_impact_report:
            parts.append("\n=== revision_impact_report (Claude artifact; prefer for what changed) ===")
            parts.append(_json_preview(self.revision_impact_report))
            self.register_artifact("revision_impact_report")

        if self.confidence_summary:
            parts.append("\n=== confidence_summary (Claude artifact) ===")
            parts.append(_json_preview(self.confidence_summary))
            self.register_artifact("confidence_summary")

        if self.review_flags:
            parts.append("\n=== review_flags (Claude artifact) ===")
            parts.append(_json_preview(self.review_flags))
            self.register_artifact("review_flags")

        if self.version_processing_metadata:
            parts.append("\n=== version_processing_metadata (compact) ===")
            parts.append(_json_preview(self.version_processing_metadata, max_chars=4000))
            self.register_artifact("version_processing_metadata")

        if self.extraction_summary:
            parts.append("\n=== clinical summary (extraction) ===")
            parts.append(self.extraction_summary[:6000])
            self.register_artifact("extraction_summary")

        if self.executive_summary:
            parts.append("\n=== executive_summary (extraction) ===")
            parts.append(self.executive_summary[:4000])
            self.register_artifact("executive_summary")

        parts.append("\n=== CONTRADICTIONS (extraction) ===")
        parts.append(f"Count: {self.contradictions_count}")
        if self.contradictions:
            parts.append(_json_preview(self.contradictions[:50], max_chars=6000))
            self.register_artifact("contradictions")

        parts.append("\n=== DASHBOARD_EXTRACTION_BULLETS ===")
        parts.append(self.dashboard_extraction_bullets)

        return "\n".join(parts)


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

    lineage_parts = []
    for v in versions:
        tag = "LIVE" if live and v.id == live.id else "draft" if v.status != CaseVersionStatus.READY else "ready"
        lineage_parts.append(f"  - v{v.version_number} id={v.id} status={v.status.value} [{tag}]")
    lineage_text = "Version lineage:\n" + "\n".join(lineage_parts)

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
