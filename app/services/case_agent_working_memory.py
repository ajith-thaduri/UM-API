"""
Bounded working memory for case Ask AI (version-scoped chat).
Stored in assistant message agent_metadata; not a second source of truth.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Keep small so Tier-1 prompts stay efficient
DEFAULT_MAX_SUMMARY_CHARS = 1200
DEFAULT_MAX_TOPICS = 8


def format_working_memory_for_prompt(
    messages: List[Any],
    *,
    max_chars: int = 1500,
) -> str:
    """
    Build a short, bounded block from the latest assistant message's working_memory
    (version-scoped rolling summary from prior turns).
    """
    for msg in reversed(messages):
        if getattr(msg, "role", None) != "assistant":
            continue
        meta = getattr(msg, "agent_metadata", None) or {}
        if not isinstance(meta, dict):
            continue
        wm = meta.get("working_memory")
        if not isinstance(wm, dict):
            continue
        if not (wm.get("summary") or wm.get("topics") or wm.get("last_pages")):
            continue
        parts: List[str] = []
        if wm.get("summary"):
            parts.append(f"Recent conversation focus: {wm['summary']}")
        topics = wm.get("topics")
        if isinstance(topics, list) and topics:
            parts.append("Related topics: " + ", ".join(str(t) for t in topics[:8]))
        pages = wm.get("last_pages")
        if isinstance(pages, list) and pages:
            parts.append(
                "Recently referenced pages: " + ", ".join(str(p) for p in pages[:6])
            )
        out = "\n".join(parts).strip()
        return out[:max_chars] if out else ""
    return ""


def extract_working_memory_summary_from_messages(
    messages: List[Any],
    max_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
) -> str:
    """Walk newest assistant messages for agent_metadata.working_memory.summary."""
    for msg in reversed(messages):
        if getattr(msg, "role", None) != "assistant":
            continue
        meta = getattr(msg, "agent_metadata", None) or {}
        if not isinstance(meta, dict):
            continue
        wm = meta.get("working_memory")
        if isinstance(wm, dict) and wm.get("summary"):
            s = str(wm["summary"]).strip()
            if s:
                return s[:max_chars]
    return ""


def merge_working_memory(
    prev: Optional[Dict[str, Any]],
    *,
    question: str,
    answer: str,
    resolved_intent: Optional[str],
    sources: Optional[List[Dict[str, Any]]],
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
    max_topics: int = DEFAULT_MAX_TOPICS,
) -> Dict[str, Any]:
    """
    Append-style compression: short summary line + topics + last cited pages.
    """
    prev = prev if isinstance(prev, dict) else {}
    prev_summary = str(prev.get("summary") or "")
    prev_topics = prev.get("topics") if isinstance(prev.get("topics"), list) else []
    prev_pages = prev.get("last_pages") if isinstance(prev.get("last_pages"), list) else []

    topics = [str(t) for t in prev_topics if t][:max_topics]
    q_short = _one_line(question, 120)
    a_short = _one_line(answer, 200)
    new_line = f"Q: {q_short} → {a_short}"
    combined = (prev_summary + " | " + new_line).strip(" |") if prev_summary else new_line
    if len(combined) > max_summary_chars:
        combined = combined[-max_summary_chars:]

    # Very light topic extraction from question
    for token in re.findall(r"\b[a-z]{4,}\b", question.lower()):
        if token in _STOPWORDS:
            continue
        if token not in topics:
            topics.append(token)
        if len(topics) >= max_topics:
            break

    pages: List[str] = []
    for p in prev_pages:
        if isinstance(p, str) and p:
            pages.append(p)
    if sources:
        for s in sources[:5]:
            if not isinstance(s, dict):
                continue
            pg = s.get("page_number")
            if pg is not None:
                pages.append(f"p.{pg}")
    pages = list(dict.fromkeys(pages))[:6]

    return {
        "summary": combined[:max_summary_chars],
        "topics": topics[:max_topics],
        "last_pages": pages,
        "last_intent": resolved_intent,
    }


def _one_line(text: str, max_len: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


_STOPWORDS = frozenset(
    {
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "does",
        "did",
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "were",
        "patient",
        "case",
        "version",
        "about",
        "tell",
        "show",
        "list",
        "please",
        "the",
        "and",
        "for",
    }
)
