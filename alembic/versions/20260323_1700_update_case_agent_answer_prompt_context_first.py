"""Update case_agent_answer prompt to use case-context-first behavior."""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "update_case_agent_prompt_v2"
down_revision: Union[str, None] = "seed_case_agent_prompt_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASE_AGENT_TEMPLATE = """User question: {question}

Prior conversation:
{history_text}

Case Context (primary source):
{structured_case_context}

Retrieved evidence chunks (only for source/page grounding or when Case Context is insufficient):
{formatted_context}

Classified intent hint: {intent_hint}

Answer using ONLY the case materials above.
Start with Case Context first. Only rely on retrieved chunks when the user asks for evidence/page/source grounding or when Case Context is insufficient.
If the answer is not present in Case Context and no retrieved chunks are provided, say "Not documented in the case Context."
For version questions, prefer VERSION_METADATA and revision_impact_report over vague guesses.
For compare/both-versions questions, structure the answer with clear per-version sections (e.g. v1 vs v2) when two versions appear in context.
State whether key claims come from version metadata, case Context artifacts, or retrieved chunks.
"""

CASE_AGENT_SYSTEM = """You are a clinical AI assistant for utilization management review.
Treat the provided Case Context as the primary source of truth.
Use only the provided case context, version metadata, precomputed review artifacts (revision impact, confidence, flags), and retrieved document chunks.
Use retrieved chunks only for page/source grounding or when Case Context is insufficient.
Never fabricate clinical facts. Be concise and precise.
When answering about versions or what changed between versions, ground answers in the structured VERSION_METADATA and case Context artifacts first, not generic guesses."""


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
            "description": "Tier-1 case chat: case-context-first, version-aware DB context, optional evidence retrieval.",
            "template": CASE_AGENT_TEMPLATE,
            "system_message": CASE_AGENT_SYSTEM,
            "variables": vars_json,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    vars_json = json.dumps(VARIABLES)
    conn.execute(
        text(
            """
            UPDATE prompts
            SET
                category = :category,
                name = :name,
                description = :description,
                template = :template,
                system_message = :system_message,
                variables = CAST(:variables AS json),
                is_active = true,
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "id": "case_agent_answer",
            "category": "rag",
            "name": "Case agent (dashboard Ask AI)",
            "description": "Tier-1 case chat: version-aware DB context, Claude artifacts, optional RAG chunks.",
            "template": """User question: {question}

Prior conversation:
{history_text}

{structured_case_context}

Retrieved evidence chunks (cite when used):
{formatted_context}

Classified intent hint: {intent_hint}

Answer using ONLY the case materials above. For version questions, prefer VERSION_METADATA and revision_impact_report over vague guesses.
State whether key claims come from version metadata, Claude artifacts, or retrieved chunks.
If something is not documented, say "Not documented."
""",
            "system_message": """You are a clinical AI assistant for utilization management review.
Use only the provided case context, version metadata, precomputed review artifacts (revision impact, confidence, flags), and retrieved document chunks.
Never fabricate clinical facts. Be concise and precise.
When answering about versions or what changed between versions, ground answers in the structured VERSION_METADATA and Claude pipeline artifacts first—not generic guesses.""",
            "variables": vars_json,
        },
    )
