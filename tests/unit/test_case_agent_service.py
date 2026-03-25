"""Unit tests for case agent intent and deterministic answers."""

from app.services.case_agent_service import (
    classify_intent,
    context_aware_suggestions,
    user_requests_document_evidence,
    build_evidence_search_plan,
    format_search_plan_for_prompt,
    EvidenceSearchPlan,
    _try_deterministic_answer,
    assess_should_retrieve_before_compose,
    retrieval_policy,
    should_retry_with_retrieval,
)
from app.services.case_agent_context_service import CaseAgentContextBundle


def _minimal_ctx(**kwargs) -> CaseAgentContextBundle:
    defaults = dict(
        case_id="c1",
        user_id="u1",
        selected_version_id="vsel",
        selected_version_number=2,
        selected_status="ready",
        live_version_id="vlive",
        live_version_number=2,
        base_version_id="v1",
        base_version_number=1,
        version_count=2,
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
        dashboard_extraction_bullets="MEDICATIONS: 0",
        lineage_text="",
        narrative_markdown="",
        patient_name="",
        used_artifact_keys=[],
    )
    defaults.update(kwargs)
    return CaseAgentContextBundle(**defaults)


def test_classify_version_count():
    assert classify_intent("How many versions does this case have?") == "version_count"


def test_classify_live_version():
    assert classify_intent("What is the current live version?") == "live_version"


def test_classify_revision_diff():
    assert classify_intent("What changed between v1 and v2?") == "revision_diff"


def test_classify_contradictions():
    assert classify_intent("List contradictions in the chart") == "contradictions"


def test_classify_greeting():
    for q in ["Hey", "Hi!", "Hello", "hey!", "good morning", "what's up", "let's start", "begin"]:
        assert classify_intent(q) == "greeting", f"Expected greeting for: {q!r}"


def test_classify_assistant_identity():
    for q in ["Who are you?", "Who r u", "what's your name", "Help", "what can you do?", "How can you help?"]:
        assert (
            classify_intent(q) == "assistant_identity"
        ), f"Expected assistant_identity for: {q!r}"


def test_deterministic_version_count():
    ctx = _minimal_ctx(version_count=3, selected_version_number=2, live_version_number=3, is_on_live=False)
    ans, blocks = _try_deterministic_answer("How many versions?", ctx, "version_count")
    assert ans and "3" in ans
    assert blocks and blocks["version_overview"]["total_versions"] == 3


def test_deterministic_live_version():
    ctx = _minimal_ctx(live_version_number=2)
    ans, blocks = _try_deterministic_answer("What is the live version?", ctx, "live_version")
    assert ans and "v2" in ans
    assert blocks["live_version"]["live_version_number"] == 2


def test_no_deterministic_for_general():
    ctx = _minimal_ctx()
    ans, blocks = _try_deterministic_answer("What meds is the patient on?", ctx, "general_case_qa")
    assert ans is None and blocks is None


def test_deterministic_greeting_is_clean_and_contextual():
    ctx = _minimal_ctx(
        selected_version_number=4,
        version_count=3,
        patient_name="Jane Doe",
    )
    ans, blocks = _try_deterministic_answer("Hello", ctx, "greeting")
    assert ans is not None
    assert ans.startswith("Hello!")
    assert "Jane Doe" in ans
    # Must not contain pipeline jargon
    assert "case Context" not in ans
    assert "source chunks" not in ans
    assert "embedding" not in ans
    # Must mention version (markdown bold **...** so UI renders cleanly)
    assert "v4" in ans
    assert "**v4 of 3 versions**" in ans
    assert blocks is None


def test_greeting_hey_uses_hello_and_patient():
    ctx = _minimal_ctx(version_count=1, patient_name="Alex Smith")
    ans, _ = _try_deterministic_answer("Hey", ctx, "greeting")
    assert ans.startswith("Hello!")
    assert "Alex Smith" in ans


def test_greeting_suggestions_use_case_artifacts():
    ctx = _minimal_ctx(
        version_count=2,
        revision_impact_report={"foo": "bar"},
        contradictions_count=2,
    )
    suggestions = context_aware_suggestions("greeting", ctx)
    assert len(suggestions) <= 3
    assert any("changed" in s.lower() or "revision" in s.lower() for s in suggestions)
    assert any("contradiction" in s.lower() for s in suggestions)


def test_greeting_suggestions_fallback_when_no_artifacts():
    ctx = _minimal_ctx(version_count=1)
    suggestions = context_aware_suggestions("greeting", ctx)
    assert len(suggestions) <= 3
    assert all(isinstance(s, str) and s for s in suggestions)


def test_deterministic_assistant_identity_is_clean():
    ctx = _minimal_ctx()
    ans, blocks = _try_deterministic_answer("Who are you?", ctx, "assistant_identity")
    assert ans is not None
    assert "source chunks" not in ans.lower()
    assert "embedding" not in ans.lower()
    assert blocks is None


def test_identity_suggestions_are_contextual():
    ctx = _minimal_ctx(
        contradictions_count=2,
        version_count=3,
    )
    suggestions = context_aware_suggestions("assistant_identity", ctx)
    assert len(suggestions) <= 3
    assert any("contradiction" in s.lower() for s in suggestions)


def test_general_qa_prefers_case_context_before_retrieval():
    retrieve, reason = retrieval_policy("general_case_qa", "What medications is the patient on?", False)
    assert retrieve is False
    assert "summary" in reason.lower()


def test_assess_narrative_first_general_qa():
    ctx = _minimal_ctx(narrative_markdown="Patient has diabetes.")
    r, reason = assess_should_retrieve_before_compose("general_case_qa", "What is the diagnosis?", ctx, False)
    assert r is False
    assert "summary" in reason.lower()


def test_assess_retrieves_when_no_narrative():
    ctx = _minimal_ctx(narrative_markdown="")
    r, _ = assess_should_retrieve_before_compose("general_case_qa", "Any allergies?", ctx, False)
    assert r is True


def test_assess_evidence_lookup():
    ctx = _minimal_ctx()
    r, _ = assess_should_retrieve_before_compose("evidence_lookup", "What page mentions aspirin?", ctx, False)
    assert r is True


def test_user_requests_document_evidence_where_documented():
    assert user_requests_document_evidence("Where is ECG data documented?")
    assert user_requests_document_evidence("Which of the documents mentions troponin?")


def test_assess_retrieves_when_question_asks_where_documented():
    ctx = _minimal_ctx(narrative_markdown="Summary mentions ECG.")
    r, reason = assess_should_retrieve_before_compose(
        "general_case_qa", "Where is ECG documented in the uploads?", ctx, False
    )
    assert r is True
    assert "document" in reason.lower()


def test_classify_evidence_lookup_where_documented():
    assert classify_intent("Where is ECG documented?") == "evidence_lookup"


def test_retry_when_no_stored_narrative():
    ctx = _minimal_ctx(narrative_markdown="")
    assert should_retry_with_retrieval("general_case_qa", "Dose?", "Some answer.", ctx=ctx)


def test_evidence_lookup_still_retrieves():
    retrieve, reason = retrieval_policy("evidence_lookup", "What page is this on?", False)
    assert retrieve is True
    assert "Page/source" in reason


def test_retry_with_retrieval_when_case_context_is_insufficient():
    assert should_retry_with_retrieval(
        "general_case_qa",
        "What medication dose is listed?",
        "Not documented in the case Context.",
    )


def test_no_retry_for_compare_when_case_context_is_primary():
    assert not should_retry_with_retrieval(
        "compare_versions",
        "What changed between v1 and v2?",
        "Not documented in the case Context.",
    )


def test_retry_when_document_evidence_question_but_retrieval_skipped():
    assert should_retry_with_retrieval(
        "general_case_qa",
        "Where is ECG documented?",
        "Only in the case summary.",
        did_initial_retrieval=False,
    )


def test_no_double_retry_when_document_evidence_already_retrieved():
    assert not should_retry_with_retrieval(
        "general_case_qa",
        "Where is ECG documented?",
        "See Document 2 page 3.",
        did_initial_retrieval=True,
    )


def test_build_evidence_search_plan_summary_first_no_retrieval():
    ctx = _minimal_ctx(narrative_markdown="Patient has hypertension.")
    p = build_evidence_search_plan("general_case_qa", "What is the blood pressure issue?", ctx)
    assert p.retrieval_required is False
    assert p.question_type == "summary_answer"
    assert p.retrieval_goal == "none"


def test_build_evidence_search_plan_evidence_lookup():
    ctx = _minimal_ctx(narrative_markdown="ECG showed sinus rhythm. Troponin negative.")
    p = build_evidence_search_plan("evidence_lookup", "Which page mentions ECG?", ctx)
    assert p.retrieval_required is True
    assert p.question_type == "evidence_lookup"
    assert p.retrieval_goal == "locate_document"
    assert "ECG" in p.embedding_query or "ecg" in p.embedding_query.lower()


def test_format_search_plan_requires_excerpts_for_pages():
    p = EvidenceSearchPlan(
        question_type="evidence_lookup",
        answer_priority="summary_first",
        retrieval_required=True,
        retrieval_goal="locate_document",
        retrieval_reason="test",
        user_focus_terms=["temperature"],
        summary_guided_terms=["febrile"],
        embedding_query="q",
        lexical_terms=["temperature", "febrile"],
    )
    text = format_search_plan_for_prompt(p)
    assert "excerpt" in text.lower() or "page" in text.lower()
    assert "summary" in text.lower()
