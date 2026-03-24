"""Seed case_agent_answer prompt for dashboard Ask AI (Tier-1 case agent)."""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "seed_case_agent_prompt_v1"
down_revision: Union[str, None] = "20260223_2100_agent_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASE_AGENT_TEMPLATE = """User question: {question}

Prior conversation:
{history_text}

{structured_case_context}

Retrieved evidence chunks (cite when used):
{formatted_context}

Classified intent hint: {intent_hint}

Answer using ONLY the case materials above. For version questions, prefer VERSION_METADATA and revision_impact_report over vague guesses.
State whether key claims come from version metadata, Claude artifacts, or retrieved chunks.
If something is not documented, say "Not documented."
"""

CASE_AGENT_SYSTEM = """You are a clinical AI assistant for utilization management review.
Use only the provided case context, version metadata, precomputed review artifacts (revision impact, confidence, flags), and retrieved document chunks.
Never fabricate clinical facts. Be concise and precise.
When answering about versions or what changed between versions, ground answers in the structured VERSION_METADATA and Claude pipeline artifacts first—not generic guesses."""


VARIABLES = [
    "question",
    "history_text",
    "structured_case_context",
    "formatted_context",
    "intent_hint",
]


def upgrade() -> None:
    conn = op.get_bind()
    vars_json = json.dumps(VARIABLES)
    conn.execute(
        text(
            """
            INSERT INTO prompts (
                id, category, name, description, template, system_message, variables, is_active, created_at, updated_at
            ) VALUES (
                :id, :category, :name, :description, :template, :system_message, CAST(:variables AS json), true, NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                category = EXCLUDED.category,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                template = EXCLUDED.template,
                system_message = EXCLUDED.system_message,
                variables = EXCLUDED.variables,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            """
        ),
        {
            "id": "case_agent_answer",
            "category": "rag",
            "name": "Case agent (dashboard Ask AI)",
            "description": "Tier-1 case chat: version-aware DB context, Claude artifacts, optional RAG chunks.",
            "template": CASE_AGENT_TEMPLATE,
            "system_message": CASE_AGENT_SYSTEM,
            "variables": vars_json,
        },
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM prompts WHERE id = 'case_agent_answer'"))
