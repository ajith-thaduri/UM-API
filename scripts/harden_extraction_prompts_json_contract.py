#!/usr/bin/env python3
"""
Harden extraction prompts so structured clinical extraction returns a single JSON object.

This script updates the live prompt records in the database and refreshes the prompt cache
for the current process. Restart the API server after running so other long-lived processes
pick up the new prompt content.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt
from app.services.prompt_service import prompt_service

BACKUP_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".prompt_backup_json_contract.json",
)

PROMPT_RULES = {
    "meds_allergies_extraction": {
        "focus": "medications and allergies",
        "empty_example": '{"medications": [], "allergies": []}',
    },
    "labs_imaging_vitals_extraction": {
        "focus": "labs, imaging, and vitals",
        "empty_example": '{"labs": [], "imaging": [], "vitals": []}',
    },
    "diagnoses_procedures_extraction": {
        "focus": "diagnoses and procedures",
        "empty_example": '{"diagnoses": [], "procedures": []}',
    },
    "history_extraction": {
        "focus": "chief complaint, history, and social factors",
        "empty_example": (
            '{"chief_complaint": null, "history_of_present_illness": null, '
            '"past_medical_history": [], "past_surgical_history": [], '
            '"family_history": [], "social_history": [], "social_factors": []}'
        ),
    },
    "therapy_notes_extraction": {
        "focus": "therapy notes and functional status",
        "empty_example": '{"therapy_notes": []}',
    },
}


def _build_system_message(focus: str) -> str:
    return f"""You are a deterministic clinical data extraction engine for {focus}.

CRITICAL OUTPUT CONTRACT:
1. Return exactly ONE JSON object at the root.
2. Never return a top-level array, markdown, prose, comments, or explanations.
3. Never return `[null]`, `[]`, `null`, or a string at the root level.
4. If a list field has no grounded items, return an empty array for that field.
5. If a scalar field is not explicitly documented, return null for that field.
6. Every array element must be an object; never emit null array entries.

GROUNDING RULES:
1. Extract ONLY information explicitly present in the provided context.
2. Do NOT infer, summarize loosely, or “complete” the chart.
3. Prefer omission over guessing.
4. Preserve dates exactly when documented; otherwise use null.
5. Do not invent clinical values, diagnoses, dates, dosages, or findings.

DEDUPLICATION RULES:
1. Extract each unique entity once per date.
2. If the same grounded fact appears multiple times, keep the most complete instance.
3. Do not duplicate the same medication, lab, diagnosis, procedure, or therapy note for the same date.
"""


def _rewrite_template(template: str, empty_example: str) -> str:
    updated = template

    replacements = {
        r"\bExtract ALL\b": "Extract only explicitly documented",
        r"\bInclude ALL\b": "Include only explicitly documented",
        r"\bALL medications\b": "explicitly documented medications",
        r"\bALL allergies\b": "explicitly documented allergies",
        r"\bALL lab results\b": "explicitly documented lab results",
        r"\bALL imaging studies\b": "explicitly documented imaging studies",
        r"\bALL vital sign measurements\b": "explicitly documented vital sign measurements",
        r"\bALL diagnoses\b": "explicitly documented diagnoses",
        r"\bALL procedures\b": "explicitly documented procedures",
    }
    for pattern, replacement in replacements.items():
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)

    strict_footer = f"""

STRICT RETURN CONTRACT:
- Return exactly one JSON object matching the schema above.
- Do not return a root array, markdown fences, commentary, or placeholder text.
- Do not output `[null]`, `[]`, or `null` at the root.
- If nothing is found for a list field, use [].
- If nothing is found for a scalar field, use null.
- Every list item must be an object; never include null entries.
- If the context does not support an item, omit that item.

VALID EMPTY RESPONSE EXAMPLE:
{empty_example}
"""

    if "STRICT RETURN CONTRACT:" not in updated:
        updated = updated.rstrip() + strict_footer

    return updated


def harden_prompts() -> None:
    db = SessionLocal()
    backup: dict[str, dict[str, str | None]] = {}
    try:
        for prompt_id, rule in PROMPT_RULES.items():
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            if not prompt:
                print(f"Skipping missing prompt: {prompt_id}")
                continue

            backup[prompt_id] = {
                "system_message": prompt.system_message,
                "template": prompt.template,
            }

            prompt.system_message = _build_system_message(rule["focus"])
            prompt.template = _rewrite_template(prompt.template or "", rule["empty_example"])
            prompt.updated_at = datetime.now(timezone.utc)
            print(f"Updated prompt: {prompt_id}")

        with open(BACKUP_FILE, "w", encoding="utf-8") as fh:
            json.dump(backup, fh, indent=2)

        db.commit()
        prompt_service.refresh_cache()
        print(f"Backup written to: {BACKUP_FILE}")
        print("Prompt cache refreshed for this process.")
        print("Restart the API server to refresh prompt cache in other running processes.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    harden_prompts()
