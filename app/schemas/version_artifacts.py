"""Contracts for version revision impact and confidence (API + persistence)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RevisionImpactReport(TypedDict, total=False):
    """Stored in CaseVersion.revision_impact_report."""

    new_documents: List[str]
    new_clinical_facts: List[str]
    updated_facts: List[str]
    confirmed_prior_facts: List[str]
    conflicts_with_prior: List[str]
    unchanged_core_story: str
    materiality_label: str
    reviewer_narrative: str
    recommended_attention_items: List[str]
    confidence_notes: str
    change_summary_one_line: str
    section_change_hints: Dict[str, str]  # section_key -> unchanged | updated | new | needs_review


class ConfidenceSummary(TypedDict, total=False):
    """Stored in CaseVersion.confidence_summary."""

    overall_score: float
    confidence_band: str
    confidence_reason: str
    contradiction_count: int
    summary_eligibility_status: str
    low_confidence_item_count: int
    evidence_coverage_note: str


def empty_revision_impact() -> Dict[str, Any]:
    return {
        "new_documents": [],
        "new_clinical_facts": [],
        "updated_facts": [],
        "confirmed_prior_facts": [],
        "conflicts_with_prior": [],
        "unchanged_core_story": "",
        "materiality_label": "No meaningful change",
        "reviewer_narrative": "",
        "recommended_attention_items": [],
        "confidence_notes": "",
        "change_summary_one_line": "",
        "section_change_hints": {},
    }
