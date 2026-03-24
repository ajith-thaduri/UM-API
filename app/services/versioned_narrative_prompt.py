"""Prompt fragments for incremental case versions (narrative continuity + change reasoning)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.extraction import ClinicalExtraction


def build_prior_version_context_prefix(prior: Optional[ClinicalExtraction]) -> Optional[str]:
    """
    Instruct the model to keep tone/structure aligned with the prior processed version
    while allowing updates from newly added documents.
    """
    if not prior:
        return None
    summary = (prior.summary or "").strip()
    exec_sum = (getattr(prior, "executive_summary", None) or "").strip()
    parts = [
        "## Prior_version_outputs (do not discard unless new evidence contradicts)",
        "Preserve clinical narrative style, headings, and level of detail unless new documents require updates.",
        "",
    ]
    if summary:
        parts.append("### Prior clinical summary\n" + summary[:12000])
    if exec_sum:
        parts.append("\n### Prior executive summary\n" + exec_sum[:4000])
    parts.append(
        "\n### New material\n"
        "The document excerpts below include NEW uploads for this case version. "
        "Integrate them with the prior version; call out additions, corrections, and conflicts explicitly."
    )
    return "\n".join(parts)


def build_change_reasoning_skeleton(
    prior: Optional[ClinicalExtraction],
    new_file_labels: list[str],
) -> Dict[str, Any]:
    """Structured placeholder filled or refined by downstream LLM steps / jobs."""
    return {
        "new_documents": new_file_labels,
        "prior_had_extraction": prior is not None,
        "new_findings": [],
        "updated_findings": [],
        "unchanged_summary": [],
        "conflicts_with_prior": [],
        "narrative_notes": "",
    }
