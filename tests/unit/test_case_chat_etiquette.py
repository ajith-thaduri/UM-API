"""One-time version intro for case chat."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services.case_chat_etiquette import (
    maybe_prepend_first_answer_version_etiquette,
    prior_version_intro_shown,
)


@dataclass
class _M:
    role: str
    agent_metadata: Optional[Dict[str, Any]] = None


def test_prior_version_intro_shown_false():
    assert not prior_version_intro_shown([_M("user"), _M("assistant", {})])


def test_prior_version_intro_shown_true():
    assert prior_version_intro_shown(
        [_M("assistant", {"case_version_intro_shown": True})]
    )


def test_prepends_once():
    hist = [_M("user"), _M("assistant", {"resolved_intent": "greeting"})]
    out, shown = maybe_prepend_first_answer_version_etiquette(
        "Beta blockers listed.",
        messages=hist,
        resolved_intent="general_case_qa",
        active_version_summary={"selected_version_number": 2},
    )
    assert shown is True
    assert out.startswith("You're on **version 2**")
    assert "Beta blockers" in out


def test_skips_after_flag():
    hist = [
        _M("assistant", {"case_version_intro_shown": True}),
    ]
    out, shown = maybe_prepend_first_answer_version_etiquette(
        "Second answer.",
        messages=hist,
        resolved_intent="general_case_qa",
        active_version_summary={"selected_version_number": 2},
    )
    assert shown is False
    assert out == "Second answer."


def test_skips_greeting_intent():
    out, shown = maybe_prepend_first_answer_version_etiquette(
        "Hello!",
        messages=[],
        resolved_intent="greeting",
        active_version_summary={"selected_version_number": 1},
    )
    assert shown is False
    assert out == "Hello!"
