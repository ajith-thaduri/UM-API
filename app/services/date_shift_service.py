"""Date shifting for HIPAA Tier 2: shift dates before sending to Claude, reverse after.

Each case gets a unique shift_days in [0, 30]. Before Tier 2 we apply (date + shift_days);
after receiving the summary we apply (date - shift_days) so no real dates leave the boundary.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from app.utils.date_utils import normalize_date_format, parse_date_for_sort
from app.repositories.case_date_shift_repository import CaseDateShiftRepository

logger = logging.getLogger(__name__)

# Regex to find date-like substrings (order matters: longer/more specific first)
DATE_PATTERNS = [
    (re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", re.I), None),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s*\.?\s*\d{1,2},?\s+\d{4}\b", re.I), None),
    (re.compile(r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b", re.I), None),
    (re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"), None),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"), None),
    (re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b"), None),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{2}\b"), None),
]


def _parse_to_datetime(date_str: str) -> Optional[datetime]:
    if not date_str or not isinstance(date_str, str):
        return None
    normalized = normalize_date_format(date_str.strip())
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%m/%d/%Y")
    except ValueError:
        return None


def _shift_date_str(date_str: str, shift_days: int, direction: int) -> str:
    """Shift a single date string. direction: 1 = add days (to Tier 2), -1 = subtract (from Tier 2)."""
    dt = _parse_to_datetime(date_str)
    if dt is None:
        return date_str
    delta = timedelta(days=shift_days * direction)
    shifted = dt + delta
    return shifted.strftime("%m/%d/%Y")


def shift_dates_in_text(text: str, shift_days: int, direction: int) -> str:
    """Find all date-like strings in text, shift them, and return new text. direction: 1 = add, -1 = subtract."""
    if not text or shift_days == 0:
        return text
    result = text
    seen = set()
    for pattern, _ in DATE_PATTERNS:
        for m in pattern.finditer(result):
            span = m.span()
            candidate = result[span[0] : span[1]]
            if candidate in seen:
                continue
            normalized = normalize_date_format(candidate)
            if normalized:
                shifted = _shift_date_str(normalized, shift_days, direction)
                if shifted != candidate:
                    result = result[: span[0]] + shifted + result[span[1] :]
                    seen.add(candidate)
                    # Only replace first occurrence per candidate to avoid double-replace
                    break
    return result


def shift_date_value(value: Any, shift_days: int, direction: int) -> str:
    """Shift a single date value (string or datetime). Returns normalized MM/DD/YYYY."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        delta = timedelta(days=shift_days * direction)
        return (value + delta).strftime("%m/%d/%Y")
    if isinstance(value, str):
        return _shift_date_str(value, shift_days, direction)
    return str(value)


def shift_timeline_events(events: List[Dict], shift_days: int, direction: int) -> List[Dict]:
    """Return new list of events with date fields shifted. Does not mutate input."""
    if not events or shift_days == 0:
        return list(events)
    out = []
    date_keys = ["date", "event_date", "occurrence_date", "start_date"]
    for ev in events:
        if not isinstance(ev, dict):
            out.append(ev)
            continue
        new_ev = dict(ev)
        for key in date_keys:
            if key in new_ev and new_ev[key]:
                new_ev[key] = shift_date_value(new_ev[key], shift_days, direction)
        out.append(new_ev)
    return out


def shift_extracted_data_dates(data: Dict, shift_days: int, direction: int) -> Dict:
    """Return new dict with date fields shifted in procedures, vitals, etc. Does not mutate input."""
    if not data or shift_days == 0:
        return dict(data) if data else {}
    out = dict(data)
    # Procedures: list of { name, date?, ... }
    if "procedures" in out and isinstance(out["procedures"], list):
        out["procedures"] = [
            {**p, "date": shift_date_value(p.get("date"), shift_days, direction)} if isinstance(p, dict) else p
            for p in out["procedures"]
        ]
    # Vitals: list of { type, value, unit, date?, ... }
    if "vitals" in out and isinstance(out["vitals"], list):
        out["vitals"] = [
            {**v, "date": shift_date_value(v.get("date"), shift_days, direction)} if isinstance(v, dict) else v
            for v in out["vitals"]
        ]
    # request_metadata.request_date
    if "request_metadata" in out and isinstance(out["request_metadata"], dict):
        rq = dict(out["request_metadata"])
        if rq.get("request_date"):
            rq["request_date"] = shift_date_value(rq["request_date"], shift_days, direction)
        out["request_metadata"] = rq
    return out


def shift_contradictions_dates(contradictions: List[Dict], shift_days: int, direction: int) -> List[Dict]:
    """Shift any date fields in contradiction items."""
    if not contradictions or shift_days == 0:
        return list(contradictions) if contradictions else []
    out = []
    for c in contradictions:
        if not isinstance(c, dict):
            out.append(c)
            continue
        new_c = dict(c)
        for key in ["date", "event_date"]:
            if key in new_c and new_c[key]:
                new_c[key] = shift_date_value(new_c[key], shift_days, direction)
        out.append(new_c)
    return out


class DateShiftService:
    """Service for per-case date shift and apply/reverse in payloads."""

    def __init__(self):
        self._repo = CaseDateShiftRepository()

    def get_or_create_shift_days(self, db, case_id: str) -> int:
        return self._repo.get_or_create_shift_days(db, case_id)

    def format_timeline_for_prompt(self, timeline_events: List[Dict]) -> str:
        """Format timeline events as text for prompt (caller must pass already-shifted events)."""
        lines = []
        for event in timeline_events:
            date = event.get("date", "Unknown date")
            desc = event.get("description", "No description")
            event_type = event.get("event_type", "")
            lines.append(f"- {date}: [{event_type}] {desc}")
        return "\n".join(lines) if lines else "No timeline events available"

    def prepare_tier2_variables(
        self,
        extracted_data: Dict,
        timeline: List[Dict],
        contradictions: List[Dict],
        shift_days: int,
    ) -> Dict[str, Any]:
        """
        Build prompt variables for Tier 2 with:
        - patient_name -> "Patient", case_number -> "Case Reference"
        - All dates shifted by shift_days (direction=1)
        - No other PHI (diagnoses/meds/labs stay as clinical terms only; no names/IDs).
        """
        shifted_data = shift_extracted_data_dates(extracted_data, shift_days, direction=1)
        shifted_timeline = shift_timeline_events(timeline, shift_days, direction=1)
        shifted_contradictions = shift_contradictions_dates(contradictions, shift_days, direction=1)

        diagnoses = shifted_data.get("diagnoses", [])
        diagnoses_text = []
        for dx in diagnoses:
            if isinstance(dx, str):
                diagnoses_text.append(dx)
            elif isinstance(dx, dict) and dx.get("name"):
                diagnoses_text.append(dx["name"])
        diagnoses_str = ", ".join(diagnoses_text) if diagnoses_text else "Not explicitly documented"

        meds = shifted_data.get("medications", [])
        meds_summary = ["- {} {} {}".format(m.get("name", "Unknown"), m.get("dosage", ""), m.get("frequency", "")).strip() for m in meds]
        meds_text = "\n".join(meds_summary) if meds_summary else "Not explicitly documented"

        labs = shifted_data.get("labs", [])
        abnormal_labs = [lab for lab in labs if lab.get("abnormal")]
        labs_summary = ["- {}: {} {} (ABNORMAL)".format(lab.get("test_name", "Unknown"), lab.get("value", ""), lab.get("unit", "")) for lab in abnormal_labs]
        labs_text = "\n".join(labs_summary) if labs_summary else "No abnormal labs"

        procedures = shifted_data.get("procedures", [])
        procedures_summary = []
        for proc in procedures:
            name = proc.get("name", "") if isinstance(proc, dict) else str(proc)
            if name:
                date = proc.get("date", "") if isinstance(proc, dict) else ""
                procedures_summary.append(f"- {name} (Date: {date})" if date else f"- {name}")
        procedures_text = "\n".join(procedures_summary) if procedures_summary else "Not explicitly documented"

        vitals = shifted_data.get("vitals", [])[:10]
        vitals_summary = []
        for vital in vitals:
            if isinstance(vital, dict) and vital.get("type") and vital.get("value"):
                date = vital.get("date", "")
                vitals_summary.append(
                    "- {}: {} {} (Date: {})".format(vital["type"], vital["value"], vital.get("unit", ""), date)
                    if date
                    else "- {}: {} {}".format(vital["type"], vital["value"], vital.get("unit", ""))
                )
        vitals_text = "\n".join(vitals_summary) if vitals_summary else "Not explicitly documented"

        timeline_text = self.format_timeline_for_prompt(shifted_timeline)
        contradictions_text_lines = []
        for c in shifted_contradictions:
            desc = c.get("description", "No description")
            suggestion = c.get("suggestion", "")
            contradictions_text_lines.append(f"- {desc} ({suggestion})" if suggestion else f"- {desc} (May require review)")
        contradictions_text = "\n".join(contradictions_text_lines) if contradictions_text_lines else "No potential missing information identified"

        allergies = shifted_data.get("allergies", [])
        allergy_names = []
        for a in allergies:
            if isinstance(a, str):
                allergy_names.append(a)
            elif isinstance(a, dict) and a.get("allergen"):
                allergy_names.append(a["allergen"])
        allergies_text = ", ".join(allergy_names) if allergy_names else "Not explicitly documented"

        request_metadata = shifted_data.get("request_metadata", {})
        request_type = request_metadata.get("request_type", "Not specified")
        requested_service = request_metadata.get("requested_service", "Not specified")
        request_date = request_metadata.get("request_date", "Not specified")
        urgency = request_metadata.get("urgency", "Routine")

        return {
            "patient_name": "Patient",
            "case_number": "Case Reference",
            "diagnoses_str": diagnoses_str,
            "meds_text": meds_text,
            "allergies_text": allergies_text,
            "procedures_text": procedures_text,
            "labs_text": labs_text,
            "vitals_text": vitals_text,
            "timeline_text": timeline_text,
            "contradictions_text": contradictions_text,
            "diagnoses_count": len(diagnoses),
            "meds_count": len(meds),
            "procedures_count": len(procedures),
            "labs_total_count": len(labs),
            "labs_abnormal_count": len(abnormal_labs),
            "timeline_count": len(timeline),
            "request_type": request_type,
            "requested_service": requested_service,
            "request_date": request_date,
            "urgency": urgency,
        }

    def reidentify_summary_text(self, summary_text: str, shift_days: int) -> str:
        """Reverse date shift in Tier 2 response so dates are restored for the client."""
        if not summary_text or shift_days == 0:
            return summary_text
        return shift_dates_in_text(summary_text, shift_days, direction=-1)


date_shift_service = DateShiftService()
