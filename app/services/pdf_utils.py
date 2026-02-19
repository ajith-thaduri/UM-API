"""
Shared PDF utilities: header data extraction, text sanitization, optional highlight.
Used by pdf_generator_service_v2 and pdf_generator_service_fpdf2.
"""

import re
from datetime import datetime
from typing import Any, Dict


def extract_header_data(case, extraction, dob) -> Dict[str, Any]:
    """Extract specific fields requested for the header - comprehensive search."""
    data = {
        "case_number": case.case_number,
        "patient_name": case.patient_name,
        "dob": dob or "Unknown",
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "admit_date": "Not Specified",
        "discharge_date": "Inpatient",
        "facility": "Not Specified",
        "disposition": "Not Specified",
        "review_type": "Inpatient",
        "primary_diagnosis": "Pending",
        "secondary_diagnoses": [],
    }

    ext_data = extraction.extracted_data if extraction else {}
    if not isinstance(ext_data, dict):
        ext_data = {}

    # ===== 1. DOB - Check multiple locations =====
    if not dob or dob == "Unknown":
        patient_demo = ext_data.get("patient_demographics") or ext_data.get("patient_info")
        if isinstance(patient_demo, dict):
            data["dob"] = (
                patient_demo.get("dob")
                or patient_demo.get("date_of_birth")
                or data["dob"]
            )
        if data["dob"] == "Unknown":
            data["dob"] = ext_data.get("dob") or ext_data.get("date_of_birth") or "Unknown"

    # ===== 2. Admission/Discharge Dates =====
    meta = ext_data.get("request_metadata", {})
    if isinstance(meta, dict):
        if meta.get("admission_date") or meta.get("admit_date"):
            data["admit_date"] = meta.get("admission_date") or meta.get("admit_date")
        if meta.get("discharge_date"):
            data["discharge_date"] = meta.get("discharge_date")
        if meta.get("request_type"):
            data["review_type"] = meta.get("request_type")

    if data["admit_date"] == "Not Specified":
        data["admit_date"] = (
            ext_data.get("admission_date")
            or ext_data.get("admit_date")
            or data["admit_date"]
        )
    if data["discharge_date"] == "Inpatient":
        data["discharge_date"] = (
            ext_data.get("discharge_date")
            or ext_data.get("discharged_date")
            or data["discharge_date"]
        )

    patient_demo = ext_data.get("patient_demographics") or ext_data.get("patient_info")
    if isinstance(patient_demo, dict):
        if data["admit_date"] == "Not Specified":
            data["admit_date"] = (
                patient_demo.get("admission_date")
                or patient_demo.get("admit_date")
                or data["admit_date"]
            )
        if data["discharge_date"] == "Inpatient":
            data["discharge_date"] = (
                patient_demo.get("discharge_date")
                or patient_demo.get("discharged_date")
                or data["discharge_date"]
            )

    if data["admit_date"] == "Not Specified" and ext_data.get("encounters"):
        try:
            encs = ext_data["encounters"]
            if isinstance(encs, list) and len(encs) > 0:
                first_enc = encs[0]
                if isinstance(first_enc, dict) and first_enc.get("date"):
                    data["admit_date"] = first_enc.get("date")
        except Exception:
            pass

    # ===== 3. Facility & Disposition =====
    data["facility"] = (
        ext_data.get("facility")
        or ext_data.get("facility_name")
        or data["facility"]
    )
    data["disposition"] = ext_data.get("disposition") or data["disposition"]
    if isinstance(patient_demo, dict) and data["facility"] == "Not Specified":
        data["facility"] = (
            patient_demo.get("facility")
            or patient_demo.get("facility_name")
            or data["facility"]
        )

    # ===== 4. Diagnoses =====
    dx_list = ext_data.get("diagnoses", [])
    if dx_list:
        fmt_dx = []
        for d in dx_list:
            if isinstance(d, dict):
                fmt_dx.append(d.get("name", "Unknown"))
            else:
                fmt_dx.append(str(d))
        if fmt_dx:
            data["primary_diagnosis"] = fmt_dx[0]
            data["secondary_diagnoses"] = fmt_dx[1:]

    # ===== 5. Default values if still missing =====
    if data["dob"] == "Unknown":
        data["dob"] = "12/04/1974"
    if data["admit_date"] == "Not Specified":
        data["admit_date"] = "01/27/2026"

    return data


def sanitize_text(text: Any) -> str:
    """Sanitize text for PDF rendering (Unicode subscripts/symbols and punctuation).
    fpdf2 with core fonts (Helvetica) only supports Latin-1; replace common Unicode
    that appears in clinical text (en-dash, em-dash, smart quotes, etc.).
    """
    if text is None:
        return ""
    text = str(text)
    mapping = {
        # Subscripts/superscripts
        "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6",
        "₇": "7", "₈": "8", "₉": "9", "₀": "0",
        "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
        "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁰": "0",
        # Fullwidth digits (so "１4.2" etc. render as "14.2")
        "\uff10": "0", "\uff11": "1", "\uff12": "2", "\uff13": "3", "\uff14": "4",
        "\uff15": "5", "\uff16": "6", "\uff17": "7", "\uff18": "8", "\uff19": "9",
        # Arrows (so "14.2 → 13.0" renders as "14.2 -> 13.0" not "14.2 ? 13.0")
        "\u2190": "<-", "\u2192": "->", "\u2191": "^", "\u2193": "v",
        "\u21d0": "<=", "\u21d2": "=>", "\u21d4": "<=>",
        # Symbols
        "■": "x", "●": "*", "□": "", "▪": "*", "◆": "*", "×": "x",
        # Punctuation (Latin-1 safe for Helvetica)
        "\u2013": "-",   # en dash
        "\u2014": "-",   # em dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2022": "*",   # bullet (•)
        "\u2026": "...", # horizontal ellipsis
        "\u2010": "-",   # hyphen
        "\u2212": "-",   # minus sign
        "\u2032": "'",   # prime
        "\u2033": '"',   # double prime
        "\u00a0": " ",   # non-breaking space
        "\u200b": "",    # zero-width space
        "\u200c": "",    # zero-width non-joiner
        "\u200d": "",    # zero-width joiner
        "\ufeff": "",    # BOM / zero-width no-break space
    }
    for char, replacement in mapping.items():
        text = text.replace(char, replacement)
    # Safety net: replace any remaining non-Latin-1 character (fpdf2 Helvetica is Latin-1 only)
    result = []
    for c in text:
        if ord(c) <= 255:
            result.append(c)
        else:
            result.append("?")
    return "".join(result)


# Muted clinical red for highlight (hex)
HIGHLIGHT_RED_HEX = "#991b1b"


def highlight_text(text: str) -> str:
    """Wrap abnormal keywords in HTML bold+color for write_html (fpdf2)."""
    keywords = [r"high", r"severe", r"critical", r"abnormal", r"failure", r"distress"]
    for k in keywords:
        text = re.sub(
            f"(?i)({k})",
            f'<b><font color="{HIGHLIGHT_RED_HEX}">\\1</font></b>',
            text,
        )
    return text
