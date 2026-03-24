"""Generate revision impact report and assemble confidence/review flags for a case version."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.case_version import CaseVersion
from app.models.extraction import ClinicalExtraction
from app.schemas.version_artifacts import empty_revision_impact
from app.services.llm.llm_factory import get_tier1_llm_service_for_user
from app.services.llm_utils import extract_json_from_response
from app.services.version_merge_service import _new_document_names_for_version

logger = logging.getLogger(__name__)

MATERIALITY_VALUES = {
    "no_meaningful_change",
    "minor_update",
    "moderate_clinical_update",
    "major_clinical_change",
    "conflict_requires_review",
}


def _count_low_confidence_items(extracted_data: Optional[Dict]) -> int:
    if not extracted_data or not isinstance(extracted_data, dict):
        return 0
    n = 0
    for key in (
        "medications",
        "labs",
        "diagnoses",
        "procedures",
        "vitals",
        "allergies",
        "imaging",
    ):
        for item in extracted_data.get(key) or []:
            if not isinstance(item, dict):
                continue
            try:
                sc = float(item.get("confidence_score", 1.0))
            except (TypeError, ValueError):
                sc = 1.0
            if sc < 0.5:
                n += 1
    return n


def _strip_summary_body(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.strip()
    if t.startswith("{") and '"markdown"' in t:
        try:
            parsed = json.loads(t)
            if isinstance(parsed, dict) and parsed.get("markdown"):
                return str(parsed["markdown"])[:8000]
        except (json.JSONDecodeError, TypeError):
            pass
    return t[:8000]


def compute_confidence_summary(
    extraction: ClinicalExtraction,
    contradictions: Optional[List],
) -> Dict[str, Any]:
    sm = extraction.source_mapping or {}
    doc_conf = sm.get("document_confidence")
    try:
        doc_conf_f = float(doc_conf) if doc_conf is not None else 1.0
    except (TypeError, ValueError):
        doc_conf_f = 1.0

    low_n = _count_low_confidence_items(extraction.extracted_data)
    ccount = len(contradictions or [])

    # Heuristic overall score (no OCR in core yet)
    base = 0.88
    base -= min(0.25, (1.0 - doc_conf_f) * 0.5)
    base -= min(0.15, ccount * 0.03)
    base -= min(0.12, low_n * 0.01)
    overall = max(0.35, min(0.98, base))

    if overall >= 0.82:
        band = "high"
    elif overall >= 0.65:
        band = "medium"
    else:
        band = "low"

    reasons: List[str] = []
    if sm.get("summary_eligibility_status") == "gated":
        reasons.append("Document text quality may limit some details; summary was still generated from available evidence.")
    if ccount:
        reasons.append(f"{ccount} potential documentation issue(s) flagged for review.")
    if low_n:
        reasons.append(f"{low_n} extracted item(s) have lower confidence scores.")

    return {
        "overall_score": round(overall, 2),
        "confidence_band": band,
        "confidence_reason": " ".join(reasons) if reasons else "Standard extraction and summary quality.",
        "contradiction_count": ccount,
        "summary_eligibility_status": sm.get("summary_eligibility_status", "eligible"),
        "low_confidence_item_count": low_n,
        "document_confidence": round(doc_conf_f, 3),
        "evidence_coverage_note": "Review source-linked entities in Clinical Data for full provenance.",
    }


def build_review_flags(
    extraction: ClinicalExtraction,
    contradictions: Optional[List],
    confidence_summary: Dict[str, Any],
) -> List[str]:
    flags: List[str] = []
    sm = extraction.source_mapping or {}
    if sm.get("summary_eligibility_status") == "gated":
        flags.append("Text quality warning: some sections may be less detailed.")
    if contradictions:
        flags.append("Documentation review: potential missing info or inconsistencies flagged.")
    if confidence_summary.get("low_confidence_item_count", 0) > 10:
        flags.append("Many low-confidence extractions: spot-check key facts against source documents.")
    if confidence_summary.get("confidence_band") == "low":
        flags.append("Overall confidence is low: prioritize manual review before decisions.")
    return flags


def _normalize_materiality(raw: Optional[str]) -> str:
    if not raw:
        return "minor_update"
    s = raw.strip().lower().replace(" ", "_")
    mapping = {
        "nomeaningfulchange": "no_meaningful_change",
        "no_meaningful_change": "no_meaningful_change",
        "minorupdate": "minor_update",
        "minor_update": "minor_update",
        "moderateclinicalupdate": "moderate_clinical_update",
        "moderate_clinical_update": "moderate_clinical_update",
        "majorclinicalchange": "major_clinical_change",
        "major_clinical_change": "major_clinical_change",
        "conflictrequiresreview": "conflict_requires_review",
        "conflict_requires_review": "conflict_requires_review",
    }
    return mapping.get(s, "minor_update")


def _display_materiality(key: str) -> str:
    return {
        "no_meaningful_change": "No meaningful change",
        "minor_update": "Minor update",
        "moderate_clinical_update": "Moderate clinical update",
        "major_clinical_change": "Major clinical change",
        "conflict_requires_review": "Conflict requires review",
    }.get(key, "Minor update")


async def generate_revision_impact_llm(
    db: Session,
    *,
    case_id: str,
    user_id: str,
    case_version_id: str,
    new_document_names: List[str],
    prior_summary: str,
    prior_executive: str,
    current_summary: str,
    current_executive: str,
    prior_contradiction_count: int,
    current_contradiction_count: int,
    merged_clinical_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call Tier-1 LLM for structured revision impact (reviewer language)."""
    llm = get_tier1_llm_service_for_user(db, user_id)
    if not llm.is_available():
        logger.warning("[VersionImpact] Tier1 LLM unavailable — using heuristic impact")
        return _heuristic_impact(
            new_document_names,
            prior_contradiction_count,
            current_contradiction_count,
        )

    schema_hint = """
Return ONLY valid JSON with these keys (arrays of short strings, reviewer-friendly plain English):
{
  "materiality_label": "one of: no_meaningful_change | minor_update | moderate_clinical_update | major_clinical_change | conflict_requires_review",
  "reviewer_narrative": "2-6 short paragraphs explaining what changed for a utilization reviewer",
  "new_clinical_facts": [],
  "updated_facts": [],
  "confirmed_prior_facts": [],
  "conflicts_with_prior": [],
  "unchanged_core_story": "one paragraph",
  "recommended_attention_items": [],
  "confidence_notes": "what a reviewer should double-check",
  "change_summary_one_line": "single line for the version header",
  "section_change_hints": { "PATIENT_OVERVIEW": "unchanged|updated|new|needs_review", ... }
}
""".strip()

    user = f"""You compare a PRIOR approved case version with the CURRENT version after new documents were added.

New document file names: {json.dumps(new_document_names)}

PRIOR executive summary (baseline):
{prior_executive[:6000]}

PRIOR full summary (baseline):
{prior_summary[:12000]}

CURRENT executive summary (after new docs):
{current_executive[:6000]}

CURRENT full summary (after new docs):
{current_summary[:12000]}

Prior contradiction count: {prior_contradiction_count}
Current contradiction count: {current_contradiction_count}

STRUCTURED_MERGED_STATE (base vs current extraction comparison; use for factual deltas):
{(json.dumps(merged_clinical_state, indent=2, default=str)[:12000] if merged_clinical_state else "(not available)")}

{schema_hint}
"""
    try:
        response, _ = await llm.chat_completion(
            messages=[{"role": "user", "content": user}],
            system_message=(
                "You are a clinical documentation analyst helping utilization reviewers. "
                "Use simple, clear reviewer language. Never invent facts not supported by the summaries. "
                "If the new documents did not materially change the story, say so explicitly."
            ),
            temperature=0.15,
            max_tokens=4000,
        )
        data = extract_json_from_response(response)
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        mat = _normalize_materiality(str(data.get("materiality_label", "")))
        data["materiality_label"] = _display_materiality(mat)
        data["materiality_key"] = mat
        data["new_documents"] = new_document_names
        return data
    except Exception as exc:
        logger.warning("[VersionImpact] LLM impact failed: %s", exc)
        return _heuristic_impact(
            new_document_names,
            prior_contradiction_count,
            current_contradiction_count,
        )


def _heuristic_impact(
    new_docs: List[str],
    prior_cc: int,
    curr_cc: int,
) -> Dict[str, Any]:
    base = empty_revision_impact()
    base["new_documents"] = new_docs
    if curr_cc > prior_cc:
        base["materiality_label"] = "Conflict requires review"
        base["materiality_key"] = "conflict_requires_review"
        base["reviewer_narrative"] = (
            "New documentation increased the number of flagged documentation issues compared with the prior version. "
            "Review the Potential Missing Info tab and source documents."
        )
        base["change_summary_one_line"] = "New documents triggered additional documentation flags."
        base["recommended_attention_items"] = ["Review flagged documentation items."]
    elif new_docs:
        base["materiality_label"] = "Minor update"
        base["materiality_key"] = "minor_update"
        base["reviewer_narrative"] = (
            f"New document(s) were added: {', '.join(new_docs)}. "
            "Compare the updated summary with the prior version to confirm any clinical changes."
        )
        base["change_summary_one_line"] = f"Added {len(new_docs)} new document(s); see updated summary."
    else:
        base["materiality_label"] = "No meaningful change"
        base["materiality_key"] = "no_meaningful_change"
        base["change_summary_one_line"] = "No new documents in this version."
    return base


async def finalize_version_artifacts(
    db: Session,
    *,
    case_id: str,
    user_id: str,
    case_version_id: str,
) -> None:
    """Populate CaseVersion revision_impact_report, confidence_summary, review_flags, materiality_label."""
    ver = db.query(CaseVersion).filter(CaseVersion.id == case_version_id).first()
    extraction = (
        db.query(ClinicalExtraction)
        .filter(ClinicalExtraction.case_version_id == case_version_id)
        .first()
    )
    if not ver or not extraction:
        return

    contradictions = extraction.contradictions or []
    conf = compute_confidence_summary(extraction, contradictions)
    flags = build_review_flags(extraction, contradictions, conf)

    new_names = _new_document_names_for_version(db, case_version_id)

    prior = None
    if ver.base_version_id:
        prior = (
            db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.case_version_id == ver.base_version_id)
            .first()
        )

    if prior:
        prior_cc = len(prior.contradictions or []) if prior else 0
        merged = getattr(extraction, "merged_clinical_state", None)
        merged_dict = merged if isinstance(merged, dict) else None
        impact = await generate_revision_impact_llm(
            db,
            case_id=case_id,
            user_id=user_id,
            case_version_id=case_version_id,
            new_document_names=new_names,
            prior_summary=_strip_summary_body(prior.summary if prior else None),
            prior_executive=_strip_summary_body(
                getattr(prior, "executive_summary", None) if prior else None
            ),
            current_summary=_strip_summary_body(extraction.summary),
            current_executive=_strip_summary_body(extraction.executive_summary),
            prior_contradiction_count=prior_cc,
            current_contradiction_count=len(contradictions),
            merged_clinical_state=merged_dict,
        )
        mat_key = impact.get("materiality_key") or _normalize_materiality(
            str(impact.get("materiality_label", ""))
        )
        ver.materiality_label = _display_materiality(mat_key)
        ver.revision_impact_report = impact
        one_line = impact.get("change_summary_one_line") or ver.change_summary
        if one_line:
            ver.change_summary = one_line
        # Keep change_reasoning as structured sibling for APIs that still read it
        ver.change_reasoning = {
            "revision_impact": impact,
            "new_documents": new_names,
            "prior_had_extraction": True,
        }
    else:
        # Version 1 or no incremental context
        ver.revision_impact_report = {
            "materiality_label": "Initial version",
            "materiality_key": "initial_version",
            "reviewer_narrative": "This is the first processed version of this case.",
            "new_documents": new_names,
            "change_summary_one_line": ver.change_summary or "Initial case processing complete.",
        }
        ver.materiality_label = "Initial version"
        ver.change_reasoning = {
            "revision_impact": ver.revision_impact_report,
            "new_documents": new_names,
            "prior_had_extraction": False,
        }

    ver.confidence_summary = conf
    ver.review_flags = flags
    db.add(ver)
    db.flush()
