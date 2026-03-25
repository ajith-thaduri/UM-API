"""
One-time chat etiquette (version scope notice) for case Ask AI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def prior_version_intro_shown(messages: List[Any]) -> bool:
    """True if any prior assistant turn already included the version intro."""
    for msg in messages:
        if getattr(msg, "role", None) != "assistant":
            continue
        meta = getattr(msg, "agent_metadata", None)
        if isinstance(meta, dict) and meta.get("case_version_intro_shown"):
            return True
    return False


def maybe_prepend_first_answer_version_etiquette(
    answer: str,
    *,
    messages: List[Any],
    resolved_intent: Optional[str],
    active_version_summary: Optional[Dict[str, Any]],
) -> tuple[str, bool]:
    """
    Once per conversation (per case version thread), prepend a short note that
    answers are scoped to the selected processing version.

    Skips trivial deterministic intents where it would be redundant or odd.
    """
    if prior_version_intro_shown(messages):
        return answer, False
    if resolved_intent in ("greeting", "version_count", "live_version", "error", None):
        return answer, False

    vn = (active_version_summary or {}).get("selected_version_number")
    if vn is None:
        return answer, False

    intro = (
        f"You're on **version {vn}** for this chat, and I'm answering based on that version.\n\n"
    )
    return intro + (answer or ""), True
