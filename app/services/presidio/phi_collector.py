"""
presidio/phi_collector.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Deterministic PHI collection and token generation.

Two responsibilities:
  1. _collect_known_phi  — build STRIP / IDENTITY groups from structured fields
  2. _generate_tokens    — assign [[TYPE-NN]] counter tokens to each identity
"""

from typing import Any, Dict, List
from app.utils.safe_logger import get_safe_logger

safe_logger = get_safe_logger(__name__)


def collect_known_phi(patient_name: str, case_metadata: Dict) -> Dict[str, Any]:
    """
    Collect known PHI values and group them by 'identity'.

    Strategy:
      STRIP   → emails, phones, MRNs, SSNs → [[REDACTED]]
      TOKENIZE → person names, orgs         → [[PERSON-NN]], [[ORGANIZATION-NN]]

    Returns:
        {
          'identities': [{'type', 'canonical', 'variants'}, ...],
          'strips':     [raw_string_to_redact, ...]
        }
    """
    case_metadata = case_metadata or {}
    strips: set = set()
    identities: List[Dict] = []

    # ── 1. Patient ────────────────────────────────────────────────────────────
    if patient_name:
        patient_identity: Dict = {
            "type": "PERSON", "canonical": patient_name, "variants": set()
        }
        parts = patient_name.split()
        if len(parts) >= 3:
            patient_identity["variants"].add(f"{parts[0]} {parts[-1]}")
            patient_identity["variants"].add(f"{parts[0]} {parts[1]}")

        alias = (
            case_metadata.get("Alias Used in Prior Records")
            or case_metadata.get("alias")
        )
        if alias:
            patient_identity["variants"].add(alias)
            a_parts = alias.split()
            if len(a_parts) >= 2:
                patient_identity["variants"].add(f"{a_parts[0]} {a_parts[-1]}")

        patient_identity["variants"] = list(patient_identity["variants"])
        identities.append(patient_identity)

    # ── 2. Provider ───────────────────────────────────────────────────────────
    provider = (
        case_metadata.get("provider")
        or case_metadata.get("provider_name")
        or case_metadata.get("physician")
        or case_metadata.get("doctor")
    )
    if provider:
        identities.append({"type": "PERSON", "canonical": provider, "variants": []})

    # ── 3. Emergency Contact ──────────────────────────────────────────────────
    ec_name = (
        case_metadata.get("emergency_contact_name")
        or case_metadata.get("emergency_contact")
    )
    if ec_name:
        ec_identity: Dict = {"type": "PERSON", "canonical": ec_name, "variants": set()}
        for p in ec_name.split():
            if len(p) > 2:
                ec_identity["variants"].add(p)
        ec_identity["variants"] = list(ec_identity["variants"])
        identities.append(ec_identity)

    # ── 4. Organisations ──────────────────────────────────────────────────────
    facility = case_metadata.get("facility") or case_metadata.get("facility_name")
    if facility:
        identities.append({"type": "ORGANIZATION", "canonical": facility, "variants": []})

    for org_key in [
        "employer", "employer_name", "company", "company_name",
        "workplace", "insurance_provider", "insurance_company",
        "payer", "payer_name", "insurer", "bank", "bank_name"
    ]:
        org_val = case_metadata.get(org_key)
        if org_val:
            identities.append({"type": "ORGANIZATION", "canonical": org_val, "variants": []})

    # ── 5. Strips (zero clinical value) ───────────────────────────────────────
    strip_fields = [
        "mrn", "ssn", "case_number", "phone", "email",
        "address", "zip", "city", "state", "insurance_id", "npi",
        "account_number", "health_plan_id", "dob",
        "passport", "license", "vehicle_plate",
        "SSN", "Medical Record Number (MRN)", "Case Number",
        "Health Plan ID", "Account Number", "NPI (Attending)",
    ]
    for field in strip_fields:
        val = case_metadata.get(field)
        if val:
            strips.add(str(val))

    for k, v in case_metadata.items():
        k_lower = k.lower()
        if any(x in k_lower for x in ["email", "phone", "mobile", "home", "fax"]):
            if v:
                strips.add(str(v))
        if any(x in k_lower for x in ["employer", "company", "workplace", "insurer", "payer", "bank"]):
            if v and isinstance(v, str):
                identities.append({"type": "ORGANIZATION", "canonical": v, "variants": []})

    safe_logger.info(f"Collected {len(identities)} identities and {len(strips)} strip values")
    return {"identities": identities, "strips": list(strips)}


def generate_tokens(
    data_groups: Dict[str, Any]
) -> tuple:
    """
    Generate counter-based tokens for all identity groups.

    Returns:
        (token_map, variant_token_map, strip_list)

        token_map         — {[[TYPE-NN]]: canonical_value}  (stored in vault)
        variant_token_map — {variant_string: [[TYPE-NN]]}   (for replacement)
        strip_list        — [raw_string to be redacted]
    """
    import re

    token_map: Dict[str, str] = {}
    variant_token_map: Dict[str, str] = {}
    counters: Dict[str, int] = {}
    strip_list: List[str] = data_groups.get("strips", [])

    for group in data_groups.get("identities", []):
        entity_type: str = group["type"]
        canonical: str = group["canonical"]
        variants: List[str] = group.get("variants", [])

        current_count = counters.get(entity_type, 0) + 1
        counters[entity_type] = current_count
        token = f"[[{entity_type}-{current_count:02d}]]"

        token_map[token] = canonical
        variant_token_map[canonical] = token
        for v in variants:
            if v not in variant_token_map:
                variant_token_map[v] = token

    safe_logger.info(f"Generated {len(token_map)} counter tokens")
    return token_map, variant_token_map, strip_list
