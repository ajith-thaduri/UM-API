"""Build version continuity context for incremental summaries (prior baseline + new docs)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.case_file import CaseFile
from app.models.case_version import CaseVersion, CaseVersionFile, CaseVersionFileRole
from app.models.extraction import ClinicalExtraction


def _summarize_extracted_counts(data: Optional[Dict]) -> Dict[str, int]:
    if not data or not isinstance(data, dict):
        return {}
    out = {}
    for key in (
        "diagnoses",
        "medications",
        "labs",
        "procedures",
        "vitals",
        "allergies",
        "imaging",
    ):
        v = data.get(key)
        if isinstance(v, list):
            out[key] = len(v)
    return out


def _new_document_names_for_version(db: Session, case_version_id: str) -> List[str]:
    names: List[str] = []
    rows = (
        db.query(CaseVersionFile)
        .filter(CaseVersionFile.case_version_id == case_version_id)
        .all()
    )
    for vr in rows:
        role = vr.file_role.value if hasattr(vr.file_role, "value") else str(vr.file_role)
        if role != CaseVersionFileRole.NEW.value:
            continue
        cf = db.query(CaseFile).filter(CaseFile.id == vr.case_file_id).first()
        if cf and cf.file_name:
            names.append(cf.file_name)
    return names


def _strip_summary_for_prompt(text: Optional[str], max_chars: int) -> str:
    if not text:
        return ""
    t = text.strip()
    if t.startswith("{") and '"markdown"' in t:
        try:
            parsed = json.loads(t)
            if isinstance(parsed, dict) and parsed.get("markdown"):
                t = str(parsed["markdown"])
        except (json.JSONDecodeError, TypeError):
            pass
    return t[:max_chars] + ("…" if len(t) > max_chars else "")


def build_and_persist_version_merge_context(
    db: Session,
    *,
    case_version_id: str,
    case_id: str,
) -> Dict[str, Any]:
    """
    Load prior-version narrative + structured snapshot and new doc names.
    Persists on ClinicalExtraction.version_merge_context for J5 prompts.
    """
    cv = db.query(CaseVersion).filter(CaseVersion.id == case_version_id).first()
    extraction = (
        db.query(ClinicalExtraction)
        .filter(ClinicalExtraction.case_version_id == case_version_id)
        .first()
    )
    if not extraction:
        return {}

    new_names = _new_document_names_for_version(db, case_version_id)
    prior: Optional[ClinicalExtraction] = None
    base_number: Optional[int] = None
    if cv and cv.base_version_id:
        prior = (
            db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.case_version_id == cv.base_version_id)
            .first()
        )
        bv = db.query(CaseVersion).filter(CaseVersion.id == cv.base_version_id).first()
        if bv:
            base_number = bv.version_number

    ctx: Dict[str, Any] = {
        "is_incremental": bool(cv and cv.base_version_id and prior),
        "base_version_number": base_number,
        "current_version_number": cv.version_number if cv else None,
        "new_document_names": new_names,
        "prior_summary_excerpt": _strip_summary_for_prompt(prior.summary if prior else None, 12000),
        "prior_executive_excerpt": _strip_summary_for_prompt(
            getattr(prior, "executive_summary", None) if prior else None, 4000
        ),
        "prior_extracted_counts": _summarize_extracted_counts(prior.extracted_data if prior else None),
        "prior_contradiction_count": len(prior.contradictions or []) if prior and prior.contradictions else 0,
    }
    extraction.version_merge_context = ctx
    db.add(extraction)
    db.commit()
    db.refresh(extraction)
    return ctx


def format_version_continuity_addon(ctx: Dict[str, Any]) -> str:
    """Human-readable block appended to Tier-2 summary prompts for incremental versions."""
    if not ctx.get("is_incremental"):
        return ""

    lines = [
        "## Version continuity (reviewer-grade)",
        f"This case version builds on version {ctx.get('base_version_number')}.",
        "Preserve the SAME section headings and order as the prior summary unless new evidence requires a new section.",
        "Integrate new documents into the full case story. Do not discard prior clinical content unless new documents contradict it.",
        "",
        "### New documents in this version",
        "\n".join(f"- {n}" for n in (ctx.get("new_document_names") or [])) or "(none listed)",
        "",
        "### Prior version executive summary (baseline)",
        ctx.get("prior_executive_excerpt") or "(none)",
        "",
        "### Prior version clinical summary (baseline)",
        ctx.get("prior_summary_excerpt") or "(none)",
        "",
        "### Prior extraction scale (reference only)",
        json.dumps(ctx.get("prior_extracted_counts") or {}, indent=2),
    ]
    return "\n".join(lines)


SECTION_STRUCTURE_CONTRACT = """
### Required section structure (use these headings in order)
1. PATIENT OVERVIEW
2. CHIEF COMPLAINT & PRESENTATION
3. CURRENT DIAGNOSES
4. MEDICATION SUMMARY
5. CLINICAL TIMELINE HIGHLIGHTS
6. KEY LAB/DIAGNOSTIC FINDINGS
7. PROCEDURES PERFORMED
8. POTENTIAL MISSING INFO / ITEMS THAT MAY REQUIRE REVIEW

If a section has no new information in this version, keep the heading and state that content is unchanged from the prior version summary where appropriate.
"""


def load_merge_context(db: Session, case_version_id: str) -> Tuple[Dict[str, Any], str]:
    """Return (context_dict, continuity_addon_text)."""
    extraction = (
        db.query(ClinicalExtraction)
        .filter(ClinicalExtraction.case_version_id == case_version_id)
        .first()
    )
    raw = extraction.version_merge_context if extraction else None
    ctx = raw if isinstance(raw, dict) else {}
    return ctx, format_version_continuity_addon(ctx)


LIST_KEYS = (
    "diagnoses",
    "medications",
    "labs",
    "procedures",
    "vitals",
    "allergies",
    "imaging",
    "social_factors",
)


def _entity_label(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(
            item.get("name")
            or item.get("test_name")
            or item.get("type")
            or item.get("description")
            or ""
        ).strip()
    return ""


def _normalize_label(s: str) -> str:
    return " ".join(s.lower().split())[:200]


def compute_merged_clinical_state(
    prior_ed: Optional[Dict[str, Any]],
    current_ed: Dict[str, Any],
    new_document_file_ids: List[str],
) -> Dict[str, Any]:
    """
    Compare base-version extraction to current full-version extraction.
    Produces reviewer-oriented hints and domain stats for summaries / impact.
    """
    prior_ed = prior_ed if isinstance(prior_ed, dict) else {}
    current_ed = current_ed if isinstance(current_ed, dict) else {}
    new_ids = set(new_document_file_ids or [])

    domain_stats: Dict[str, Any] = {}
    delta_by_domain: Dict[str, List[str]] = {}
    section_change_hints: Dict[str, str] = {}

    for key in LIST_KEYS:
        cur_list = current_ed.get(key) or []
        pr_list = prior_ed.get(key) or []
        if not isinstance(cur_list, list):
            cur_list = []
        if not isinstance(pr_list, list):
            pr_list = []

        prior_labels = {_normalize_label(_entity_label(x)) for x in pr_list if _entity_label(x)}
        cur_labels = {_normalize_label(_entity_label(x)) for x in cur_list if _entity_label(x)}

        new_names: List[str] = []
        for item in cur_list:
            if not isinstance(item, dict):
                continue
            fid = item.get("source_file_id")
            if fid and str(fid) in new_ids:
                lab = _entity_label(item)
                if lab:
                    new_names.append(lab)
        delta_by_domain[key] = new_names[:80]

        added = cur_labels - prior_labels
        removed = prior_labels - cur_labels
        domain_stats[key] = {
            "prior_count": len(pr_list),
            "current_count": len(cur_list),
            "net_new_distinct_labels": len(added),
            "removed_distinct_labels": len(removed),
            "items_attributed_to_new_documents": len(new_names),
        }

        if new_names or len(added) > 0 or len(removed) > 0:
            if len(added) == 0 and len(removed) == 0 and not new_names:
                section_change_hints[key.upper()] = "unchanged"
            elif new_names or len(added) > 2 or len(removed) > 1:
                section_change_hints[key.upper()] = "updated"
            else:
                section_change_hints[key.upper()] = "updated" if (new_names or added) else "unchanged"
        else:
            section_change_hints[key.upper()] = "unchanged"

    # Map clinical domains to summary section hints (coarse)
    if any(section_change_hints.get(k) == "updated" for k in ("DIAGNOSES", "MEDICATIONS")):
        section_change_hints.setdefault("CURRENT_DIAGNOSES", "updated")
        section_change_hints.setdefault("MEDICATION_SUMMARY", "updated")
    if section_change_hints.get("LABS") == "updated" or section_change_hints.get("IMAGING") == "updated":
        section_change_hints.setdefault("KEY_LAB_DIAGNOSTIC_FINDINGS", "updated")

    lines = [
        "Merged clinical state (base + new documents):",
        f"- New document file IDs considered for delta attribution: {len(new_ids)}",
    ]
    for key in LIST_KEYS:
        st = domain_stats.get(key, {})
        if st.get("items_attributed_to_new_documents", 0) or st.get("net_new_distinct_labels", 0):
            lines.append(
                f"- {key}: prior {st.get('prior_count')} → current {st.get('current_count')}; "
                f"new-doc-tagged items: {st.get('items_attributed_to_new_documents')}; "
                f"net new labels: {st.get('net_new_distinct_labels')}"
            )

    return {
        "domain_stats": domain_stats,
        "delta_by_domain": delta_by_domain,
        "section_change_hints": section_change_hints,
        "reviewer_brief": "\n".join(lines),
    }


def format_merged_clinical_state_addon(merged: Optional[Dict[str, Any]], max_chars: int = 20000) -> str:
    if not merged or not isinstance(merged, dict):
        return ""
    try:
        body = json.dumps(merged, indent=2, default=str)
    except TypeError:
        body = str(merged)
    if len(body) > max_chars:
        body = body[:max_chars] + "…"
    return "## Merged clinical state (structured base vs current)\nUse this to preserve continuity and only expand sections that show updates.\n\n```json\n" + body + "\n```\n"


def build_and_persist_merged_clinical_state(
    db: Session,
    *,
    case_version_id: str,
) -> Dict[str, Any]:
    """Compute merged_clinical_state on the current version extraction row."""
    from app.repositories.case_version_repository import case_version_file_repository

    cv = db.query(CaseVersion).filter(CaseVersion.id == case_version_id).first()
    extraction = (
        db.query(ClinicalExtraction)
        .filter(ClinicalExtraction.case_version_id == case_version_id)
        .first()
    )
    if not extraction or not cv:
        return {}

    new_ids = case_version_file_repository.new_file_ids_for_version(db, case_version_id)
    prior: Optional[ClinicalExtraction] = None
    if cv.base_version_id:
        prior = (
            db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.case_version_id == cv.base_version_id)
            .first()
        )

    merged = compute_merged_clinical_state(
        prior.extracted_data if prior else None,
        extraction.extracted_data or {},
        new_ids,
    )
    extraction.merged_clinical_state = merged
    db.add(extraction)
    db.commit()
    db.refresh(extraction)
    return merged
