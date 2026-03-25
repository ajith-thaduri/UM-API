"""Tests for Tier-2 narrative extraction and narrative-first context channels."""

import json

from app.services.case_agent_context_service import (
    CaseAgentContextBundle,
    derive_summary_guided_lexical_terms,
    extract_tier2_summary_markdown,
    extract_user_focus_terms_from_question,
)


def test_extract_tier2_from_markdown_field():
    stored = {"markdown": "# Story\n\nPatient admitted.", "meta": 1}
    assert "Patient admitted" in extract_tier2_summary_markdown(stored)


def test_extract_tier2_from_json_string():
    s = json.dumps({"body": "Line one.\nLine two."})
    out = extract_tier2_summary_markdown(s)
    assert "Line one" in out


def test_extract_tier2_plain_text():
    assert extract_tier2_summary_markdown("  Hello world  ") == "Hello world"


def test_narrative_first_context_keys():
    ctx = CaseAgentContextBundle(
        case_id="c",
        user_id="u",
        selected_version_id="v1",
        selected_version_number=1,
        selected_status="ready",
        live_version_id="v1",
        live_version_number=1,
        base_version_id=None,
        base_version_number=None,
        version_count=1,
        is_on_live=True,
        change_summary=None,
        revision_impact_report=None,
        confidence_summary=None,
        review_flags=None,
        version_processing_metadata=None,
        extraction_summary=None,
        executive_summary="Short exec",
        contradictions=[],
        contradictions_count=0,
        dashboard_extraction_bullets="",
        lineage_text="",
        narrative_markdown="## Case\nDetails here.",
        patient_name="",
    )
    d = ctx.build_narrative_first_context(include_dashboard_context=True)
    assert "authoritative_case_summary" in d
    assert "Details here" in d["authoritative_case_summary"]
    assert "version_and_lineage" in d
    assert "revision_compare_extra" in d
    assert "search_plan_context" in d


def test_extract_user_focus_terms_generic():
    q = 'Where is the "troponin" level documented?'
    terms = extract_user_focus_terms_from_question(q)
    assert any("troponin" in t.lower() for t in terms)


def test_derive_summary_guided_lexical_neighbors():
    ctx = CaseAgentContextBundle(
        case_id="c",
        user_id="u",
        selected_version_id="v1",
        selected_version_number=1,
        selected_status="ready",
        live_version_id="v1",
        live_version_number=1,
        base_version_id=None,
        base_version_number=None,
        version_count=1,
        is_on_live=True,
        change_summary=None,
        revision_impact_report=None,
        confidence_summary=None,
        review_flags=None,
        version_processing_metadata=None,
        extraction_summary=None,
        executive_summary=None,
        contradictions=[],
        contradictions_count=0,
        dashboard_extraction_bullets="",
        lineage_text="",
        narrative_markdown="Patient had ECG in ED and troponin was ordered.",
        patient_name="",
    )
    guided = derive_summary_guided_lexical_terms(ctx, ["ECG"], max_output=12)
    assert any("troponin" in t.lower() for t in guided)
