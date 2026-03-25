"""case_agent_answer: summary-guided document search plan + location grounding rules."""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# Keep <= 32 chars (alembic_version.version_num is VARCHAR(32))
revision: str = "sg_evidence_routing_v1"
down_revision: Union[str, None] = "case_agent_narrative_first_v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASE_AGENT_TEMPLATE = """User question: {question}

Prior conversation:
{history_text}

Version-scoped working memory (compressed from earlier turns on this case version; not a separate source of truth):
{working_memory}

{search_plan_context}

=== AUTHORITATIVE STORED CASE SUMMARY (primary narrative for this version) ===
{authoritative_case_summary}

=== VERSION AND LINEAGE ===
{version_and_lineage}

=== REVIEW PIPELINE ARTIFACTS (what changed, confidence, flags) ===
{review_artifacts}

=== STRUCTURED CLINICAL FACTS (supporting; align with the summary above) ===
{structured_clinical_facts}

{revision_compare_extra}

Supporting document excerpts (retrieved for this turn when document lookup ran):
{formatted_context}

Intent hint (routing only): {intent_hint}

Instructions:
- Understand the user question first. Then use the stored case summary as the authoritative clinical story for this version.
- Follow DOCUMENT_SEARCH_PLAN above; it matches the server's tool workflow (whether document search ran and what to optimize for).
- For clinical facts, stay consistent with the summary. Do not contradict the summary.
- For document names, file numbers, or page numbers: state them only if they appear in the supporting excerpts above.
- When excerpts are present, read them for the user's topic (including common medical synonyms). Cite file/page when an excerpt clearly supports a location.
- If the summary supports a topic but no excerpt shows a clear document location, say the summary supports the topic but a matching page/document was not found in the retrieved excerpts.
- If the answer is not in the summary and excerpts do not help, say the information is not documented in the available materials for this version.
- For version-difference questions, prefer revision impact and change summaries over guesses.
- For compare questions, organize clearly by version when two versions appear above.
"""


CASE_AGENT_SYSTEM = """You are a clinical AI assistant for utilization management review.
You answer only from the materials provided: document search plan, stored case summary, version metadata, pipeline review artifacts, structured clinical facts, optional version-compare notes, prior-turn working memory, and any supporting document excerpts.
The stored case summary is authoritative for clinical facts. Document excerpts are authoritative for what appears on specific pages; never invent page or file references.
Never fabricate clinical facts. Be concise and precise."""


VARIABLES = [
    "question",
    "history_text",
    "working_memory",
    "search_plan_context",
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
            "description": "Tier-1 narrative-first chat: summary authoritative; summary-guided RAG for evidence questions.",
            "template": CASE_AGENT_TEMPLATE,
            "system_message": CASE_AGENT_SYSTEM,
            "variables": vars_json,
        },
    )


def downgrade() -> None:
    """Restore prior prompt by re-running revision case_agent_narrative_first_v3 upgrade SQL if needed."""
    pass
