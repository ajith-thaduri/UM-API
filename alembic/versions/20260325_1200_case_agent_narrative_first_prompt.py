"""Narrative-first case_agent_answer: Tier-2 summary channels + working memory."""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "case_agent_narrative_first_v3"
down_revision: Union[str, None] = "update_case_agent_prompt_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASE_AGENT_TEMPLATE = """User question: {question}

Prior conversation:
{history_text}

Version-scoped working memory (compressed from earlier turns on this case version; not a separate source of truth):
{working_memory}

=== AUTHORITATIVE STORED CASE SUMMARY (primary narrative for this version) ===
{authoritative_case_summary}

=== VERSION AND LINEAGE ===
{version_and_lineage}

=== REVIEW PIPELINE ARTIFACTS (what changed, confidence, flags) ===
{review_artifacts}

=== STRUCTURED CLINICAL FACTS (supporting; align with the summary above) ===
{structured_clinical_facts}

{revision_compare_extra}

Supporting document excerpts (use only for page references or when the summary lacks the detail the user needs):
{formatted_context}

Intent hint (routing only): {intent_hint}

Instructions:
- Treat the stored case summary as the primary story for this version. Do not invent a different clinical story.
- Use structured facts and review artifacts to enrich or support the summary; do not contradict the summary unless the user explicitly asks to audit it against source documents.
- Use supporting document excerpts to cite file/page locations or to fill gaps when the summary does not contain the answer.
- If the answer is not in the summary and no excerpts apply, say the information is not documented in the available materials for this version.
- For version-difference questions, prefer revision impact and change summaries over guesses.
- For compare questions, organize clearly by version when two versions appear above.
"""


CASE_AGENT_SYSTEM = """You are a clinical AI assistant for utilization management review.
You answer only from the materials provided: stored case summary, version metadata, pipeline review artifacts, structured clinical facts, optional version-compare notes, prior-turn working memory, and any supporting document excerpts.
The stored case summary is the primary narrative for the selected version. Use document excerpts for citations and extra detail, not to rewrite the case story.
Never fabricate clinical facts. Be concise and precise."""


VARIABLES = [
    "question",
    "history_text",
    "working_memory",
    "authoritative_case_summary",
    "version_and_lineage",
    "review_artifacts",
    "structured_clinical_facts",
    "revision_compare_extra",
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
            "description": "Tier-1 narrative-first case chat: Tier-2 summary primary, optional evidence, version-scoped memory.",
            "template": CASE_AGENT_TEMPLATE,
            "system_message": CASE_AGENT_SYSTEM,
            "variables": vars_json,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    vars_json = json.dumps(
        [
            "question",
            "history_text",
            "structured_case_context",
            "formatted_context",
            "intent_hint",
        ]
    )
    conn.execute(
        text(
            """
            UPDATE prompts
            SET
                description = :description,
                template = :template,
                system_message = :system_message,
                variables = CAST(:variables AS json),
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "id": "case_agent_answer",
            "description": "Tier-1 case chat: case-context-first, version-aware DB context, optional evidence retrieval.",
            "template": """User question: {question}

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
""",
            "system_message": """You are a clinical AI assistant for utilization management review.
Treat the provided Case Context as the primary source of truth.
Use only the provided case context, version metadata, precomputed review artifacts (revision impact, confidence, flags), and retrieved document chunks.
Use retrieved chunks only for page/source grounding or when Case Context is insufficient.
Never fabricate clinical facts. Be concise and precise.
When answering about versions or what changed between versions, ground answers in the structured VERSION_METADATA and case Context artifacts first, not generic guesses.""",
            "variables": vars_json,
        },
    )
