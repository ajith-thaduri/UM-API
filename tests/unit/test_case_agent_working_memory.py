"""Working memory merge and prompt formatting."""

from app.services.case_agent_working_memory import (
    format_working_memory_for_prompt,
    merge_working_memory,
)


class _Msg:
    def __init__(self, role: str, agent_metadata=None):
        self.role = role
        self.agent_metadata = agent_metadata


def test_merge_working_memory_rolls_summary():
    prev = {"summary": "old", "topics": ["x"], "last_pages": []}
    out = merge_working_memory(
        prev,
        question="What changed in meds?",
        answer="Dose was updated.",
        resolved_intent="general_case_qa",
        sources=[{"page_number": 3}],
    )
    assert "meds" in out["summary"].lower() or "dose" in out["summary"].lower()
    assert out["last_pages"]


def test_format_working_memory_for_prompt_reads_last_assistant():
    messages = [
        _Msg("user", None),
        _Msg(
            "assistant",
            {
                "working_memory": {
                    "summary": "Discussed labs.",
                    "topics": ["creatinine"],
                    "last_pages": ["p.2"],
                }
            },
        ),
    ]
    block = format_working_memory_for_prompt(messages)
    assert "labs" in block.lower()
    assert "creatinine" in block.lower()
