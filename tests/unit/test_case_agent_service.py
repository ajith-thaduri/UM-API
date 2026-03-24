"""Unit tests for case agent intent and deterministic answers."""

from app.services.case_agent_service import (
    classify_intent,
    context_aware_suggestions,
    _try_deterministic_answer,
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
    ctx = _minimal_ctx(selected_version_number=4, version_count=3)
    ans, blocks = _try_deterministic_answer("Hello", ctx, "greeting")
    assert ans is not None
    # Must not contain pipeline jargon
    assert "case Context" not in ans
    assert "source chunks" not in ans
    assert "embedding" not in ans
    # Must mention version
    assert "v4" in ans
    assert blocks is None


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
    assert "case Context" in reason


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
