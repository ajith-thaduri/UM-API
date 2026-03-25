"""Quick-action attachment for upload intake (case #, request type, priority)."""

from __future__ import annotations

from app.services.upload_agent_service import intake_quick_actions_for_message


def _data(**kwargs):
    base = {
        "patient_name": "P",
        "dob": "01/01/1990",
        "mrn": "M1",
        "case_number": "UM-ABC123",
        "priority": "Routine",
        "request_type": None,
        "requested_service": "UM Review",
        "request_date": "01/15/2025",
        "diagnosis": None,
        "files": [],
    }
    base.update(kwargs)
    return base


def test_request_type_buttons_when_llm_says_type_of_request_not_request_type():
    collected = _data(request_type=None)
    # Earlier required fields filled; next missing is request_type
    missing_rt = ["request_type", "requested_service", "request_date"]
    msg = (
        "Case number updated. Next, I need to know the type of request for this review."
    )
    actions = intake_quick_actions_for_message(collected, missing_rt, msg)
    labels = {a.label for a in actions}
    assert "Inpatient" in labels
    assert "Outpatient" in labels


def test_request_type_buttons_from_next_field_even_if_message_omits_keywords():
    collected = _data(request_type=None)
    missing_rt = ["request_type"]
    actions = intake_quick_actions_for_message(
        collected, missing_rt, "Could you tell me how this should be routed?"
    )
    assert len(actions) == 4
    assert actions[0].label == "Inpatient"


def test_case_number_branch_wins_when_case_still_missing_even_if_message_mentions_type():
    collected = _data(case_number=None, request_type=None)
    missing = ["case_number", "priority", "request_type", "requested_service", "request_date"]
    actions = intake_quick_actions_for_message(
        collected,
        missing,
        "What is the type of request? Also we need a case number.",
    )
    assert any("Use UM-" in a.label for a in actions)


def test_priority_from_next_field():
    collected = _data(priority=None)
    missing_pr = ["priority"]
    actions = intake_quick_actions_for_message(
        collected, missing_pr, "Almost done — how urgent is this?"
    )
    labels = {a.label for a in actions}
    assert "Routine" in labels
    assert "Urgent" in labels
