"""
presidio/service.py
━━━━━━━━━━━━━━━━━━━
Thin orchestrator — wires the sub-modules together.

Responsibilities:
  - de_identify_for_summary  (Tier 2 entry point)
  - re_identify_summary      (post-Claude re-hydration)
  - switch_ner_engine / get_engine_info (admin API pass-through)
  - Async wrappers for both public methods
"""

import asyncio
import random
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.privacy_vault import PrivacyVault
from app.services.phi_validator import phi_validator, PHILeakageError
from app.utils.safe_logger import get_safe_logger

# Sub-modules
from .constants import normalize_entity_type  # re-exported for compat
from .engine import EngineManager, PRESIDIO_AVAILABLE
from .phi_collector import collect_known_phi, generate_tokens
from .token_replacer import replace_known_phi, replace_in_string
from .ner_sanitizer import sanitize_ner_results, resolve_overlapping_spans
from .span_processor import process_residual_phi_in_string, presidio_scan_free_text
from .date_handler import shift_dates_structured, shift_dates_in_text, reverse_dates_in_text

# Custom recognizers (all in one import)
from app.services.presidio.recognizers import ALL_RECOGNIZERS

safe_logger = get_safe_logger(__name__)

_EXECUTOR: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="presidio")
    return _EXECUTOR


class PresidioDeIdentificationService:
    """
    Main de-identification service for Tier 2 (Claude) processing.

    Architecture (v2.0):
      Step 1 → Collect known PHI from structured fields
      Step 2 → Generate deterministic [[TYPE-NN]] tokens
      Step 3 → Replace known PHI in structured data
      Step 4 → Shift dates (structured fields + narrative)
      Step 5 → Presidio NER scan (catches residual leaks in free text)
      Step 5b→ De-identify document chunks
      Step 6 → Pre-flight PHI validation (fail-closed)
      Step 7 → Store in Privacy Vault
    """

    def __init__(self):
        self._engine_mgr = EngineManager(ALL_RECOGNIZERS)
        # Convenience aliases
        self.analyzer = self._engine_mgr.analyzer
        self.anonymizer = self._engine_mgr.anonymizer
        self.active_ner_engine = self._engine_mgr.active_ner_engine
        self.active_model_name = self._engine_mgr.active_model_name

        # Per-call state (refreshed on every de_identify_for_summary call)
        self._variant_token_map: Dict[str, str] = {}
        self._strip_list: List[str] = []

    @staticmethod
    def _apply_deterministic_regex(text: str) -> str:
        """Apply strict regex for explicitly labeled fields that NER struggles with."""
        import re
        
        # 1. Patient Name / Alias
        text = re.sub(r"\b(Patient(?:\s+Name)?|Name|PT):\s+([A-Z][a-z]+(?:[\s-][A-Z][a-z]+){1,3})\b", r"\1: [[PERSON-01]]", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(Alias|AKA|Also known as|Goes by):\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", r"\1: [[PERSON-01]]", text, flags=re.IGNORECASE)
        
        # 2. Relatives
        text = re.sub(r"\b(Emergency\s+Contact|Spouse|Relative)[:\s\n]+(?:Name:\s+)?[A-Z][a-z]+(?:[\s-][A-Z][a-z]+){1,2}\b", r"\1: [[REDACTED]]", text, flags=re.IGNORECASE)
        
        # 3. Employer
        text = re.sub(r"\b(Employer)[:\s]+(?:[A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+){0,3})[ \t]+(?:Corporation|Corp\.|Inc\.|LLC|Company|Logistics|Power[ \t]+Plant|Bank|Pharmacy|Group)\b", r"\1: [[ORGANIZATION-01]]", text, flags=re.IGNORECASE)
        
        # 4. Username
        text = re.sub(r"\b(Username|User\s*ID|Login|Portal\s*Username)[:\s]+[a-zA-Z0-9._-]+\b", r"\1: [[REDACTED]]", text, flags=re.IGNORECASE)
        
        return text

    # ── Admin / engine API ────────────────────────────────────────────────────

    def switch_ner_engine(self, engine_type: str = None, model_id: str = None) -> Dict[str, Any]:
        result = self._engine_mgr.switch_ner_engine(engine_type=engine_type, model_id=model_id)
        # Keep local aliases in sync
        self.analyzer = self._engine_mgr.analyzer
        return result

    def get_engine_info(self) -> Dict[str, Any]:
        return self._engine_mgr.get_engine_info()

    # ── Backward-compat method delegations ───────────────────────────────────
    # phi_validator and other callers may invoke these methods on the service instance.

    def _sanitize_ner_results(self, results, text: str):
        """Backward-compat delegate → ner_sanitizer.sanitize_ner_results"""
        return sanitize_ner_results(results, text)

    def _resolve_overlapping_spans(self, results):
        """Backward-compat delegate → ner_sanitizer.resolve_overlapping_spans"""
        return resolve_overlapping_spans(results)

    def _process_residual_phi_in_string(self, text, analyzer_results, token_map, shift_days=0, score_threshold=0.85):
        """Backward-compat delegate → span_processor.process_residual_phi_in_string"""
        return process_residual_phi_in_string(text, analyzer_results, token_map, shift_days, score_threshold)

    def _shift_dates_in_text(self, text: str, shift_days: int) -> str:
        """Backward-compat delegate → date_handler.shift_dates_in_text"""
        return shift_dates_in_text(text, shift_days)

    def _replace_in_string(self, text: str) -> str:
        """Backward-compat delegate → token_replacer.replace_in_string"""
        return replace_in_string(text, self._variant_token_map, self._strip_list)


    def de_identify_for_summary(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        patient_name: str,
        timeline: List[Dict],
        clinical_data: Dict,
        red_flags: List[Dict],
        case_metadata: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
        document_chunks: Optional[List[str]] = None,
    ) -> Tuple[Dict, str, Dict[str, str]]:
        """
        De-identify all data before sending to Tier 2 (Claude).

        Returns:
            (de_identified_payload, vault_id, token_map)
        Raises:
            PHILeakageError: if pre-flight validation detects PHI in final payload
        """
        safe_logger.info(f"Starting de-identification for case {case_id}")
        case_metadata = case_metadata or {}

        if score_threshold is None:
            score_threshold = settings.PRESIDIO_FREE_TEXT_THRESHOLD

        # Step 1: Random date-shift offset
        shift_days = random.randint(
            getattr(settings, "DATE_SHIFT_MIN_DAYS", 1),
            getattr(settings, "DATE_SHIFT_MAX_DAYS", 30),
        )
        safe_logger.info(f"shift_days={shift_days} for case {case_id}")

        # Step 2: Collect known PHI
        known_phi = collect_known_phi(patient_name, case_metadata)

        # Step 3: Generate tokens
        token_map, self._variant_token_map, self._strip_list = generate_tokens(known_phi)

        # Step 4a: Replace known PHI in structured data
        de_id_clinical = replace_known_phi(deepcopy(clinical_data), self._variant_token_map, self._strip_list)
        de_id_timeline  = replace_known_phi(deepcopy(timeline),       self._variant_token_map, self._strip_list)
        de_id_flags     = replace_known_phi(deepcopy(red_flags),      self._variant_token_map, self._strip_list)

        # Step 4b: Shift dates in structured data
        shifted_fields: List[Dict] = []
        de_id_clinical, s1 = shift_dates_structured(de_id_clinical, shift_days, "clinical_data")
        de_id_timeline,  s2 = shift_dates_structured(de_id_timeline,  shift_days, "timeline")
        de_id_flags,     s3 = shift_dates_structured(de_id_flags,     shift_days, "red_flags")
        shifted_fields.extend(s1 + s2 + s3)

        # Step 5: Presidio free-text scan (catches residual leaks)
        analyzer = self._engine_mgr.analyzer
        de_id_clinical = presidio_scan_free_text(de_id_clinical, analyzer, token_map, shift_days, score_threshold)
        de_id_timeline  = presidio_scan_free_text(de_id_timeline,  analyzer, token_map, shift_days, score_threshold)
        de_id_flags     = presidio_scan_free_text(de_id_flags,     analyzer, token_map, shift_days, score_threshold)

        # Step 5b: De-identify document chunks
        de_id_chunks: List[str] = []
        if document_chunks:
            safe_logger.info(f"De-identifying {len(document_chunks)} chunks for case {case_id}")
            for chunk in document_chunks:
                # 1. Deterministic replacement first
                de_id_chunk = replace_in_string(chunk, self._variant_token_map, self._strip_list)

                # 1.5. Deterministic Regex for tough HIPAA cases
                de_id_chunk = self._apply_deterministic_regex(de_id_chunk)

                # 2. Global date shift for standard formats
                #    We do this BEFORE NER so that process_residual_phi_in_string can skip shifted dates
                de_id_chunk = shift_dates_in_text(de_id_chunk, shift_days)

                if analyzer:
                    # 3. NER Scan (Standard dates are already shifted, residual ones like "last March" remain)
                    analyzed = analyzer.analyze(
                        text=de_id_chunk, language="en", score_threshold=score_threshold
                    )
                    # 4. Filter out entities that overlap with existing tokens [[...]]
                    token_markers = [(m.start(), m.end()) for m in re.finditer(r"\[\[.*?\]\]", de_id_chunk)]
                    from .span_processor import _overlaps_any_token
                    analyzed = [
                        r for r in analyzed if not _overlaps_any_token(r.start, r.end, token_markers)
                    ]
                    
                    if analyzed:
                        # 5. Process residual PHI (includes skip logic for already shifted dates)
                        de_id_chunk = process_residual_phi_in_string(
                            de_id_chunk, analyzed, token_map, shift_days, score_threshold
                        )
                
                de_id_chunks.append(de_id_chunk)
            safe_logger.info(f"De-identified {len(de_id_chunks)} chunks")

        # Step 6: Build payload
        payload = {
            "clinical_data": de_id_clinical,
            "timeline":      de_id_timeline,
            "red_flags":     de_id_flags,
            "document_chunks": de_id_chunks,
        }

        # Step 7: Pre-flight validation (fail-closed)
        if getattr(settings, "ENABLE_PREFLIGHT_VALIDATION", True):
            try:
                # Build flat {value: type} dict expected by phi_validator
                known_phi_flat = {}
                for identity in known_phi.get("identities", []):
                    known_phi_flat[identity["canonical"]] = identity["type"]
                    for variant in identity.get("variants", []):
                        known_phi_flat[variant] = identity["type"]
                for strip_val in known_phi.get("strips", []):
                    known_phi_flat[strip_val] = "STRIP"

                phi_validator.validate_payload(
                    payload=payload, known_phi_values=known_phi_flat,
                    case_id=case_id, allow_tokens=True,
                )
            except PHILeakageError as e:
                safe_logger.error(f"Pre-flight validation failed for case {case_id}: {e}")
                raise

        # Step 8: Store in Privacy Vault
        existing = (
            db.query(PrivacyVault)
            .filter(PrivacyVault.case_id == case_id, PrivacyVault.is_active == True)
            .all()
        )
        for v in existing:
            v.is_active = False
        if existing:
            db.flush()
            safe_logger.info(f"Deactivated {len(existing)} old vault(s) for case {case_id}")

        vault_entry = PrivacyVault(
            case_id=case_id, user_id=user_id,
            date_shift_days=shift_days, token_map=token_map,
            shifted_fields=shifted_fields, is_active=True,
        )
        db.add(vault_entry)
        db.commit()
        db.refresh(vault_entry)

        safe_logger.info(
            f"De-identification complete for {case_id}: "
            f"{len(token_map)} tokens, {len(shifted_fields)} date shifts, vault={vault_entry.id}"
        )
        return payload, vault_entry.id, token_map

    def re_identify_summary(self, db: Session, vault_id: str, summary_text: str) -> str:
        """Re-identify Claude summary using vault token map and date reversal."""
        vault = db.query(PrivacyVault).filter(PrivacyVault.id == vault_id).first()
        if not vault:
            safe_logger.error(f"Vault {vault_id} not found")
            return summary_text

        re_id = summary_text
        for token, original in vault.token_map.items():
            re_id = re.sub(re.escape(token), lambda _m, o=original: o, re_id, flags=re.IGNORECASE)

        re_id = reverse_dates_in_text(re_id, vault.date_shift_days)
        safe_logger.info(f"Re-identification complete for vault {vault_id}")
        return re_id

    # ── Async wrappers ────────────────────────────────────────────────────────

    async def de_identify_for_summary_async(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        patient_name: str,
        timeline: List[Dict],
        clinical_data: Dict,
        red_flags: List[Dict],
        case_metadata: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
        document_chunks: Optional[List[str]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> Tuple[Dict, str, Dict[str, str]]:
        """Async wrapper: runs de_identify_for_summary in thread pool."""
        loop = loop or asyncio.get_running_loop()
        fn = partial(
            self.de_identify_for_summary,
            db=db, case_id=case_id, user_id=user_id, patient_name=patient_name,
            timeline=timeline, clinical_data=clinical_data, red_flags=red_flags,
            case_metadata=case_metadata, score_threshold=score_threshold,
            document_chunks=document_chunks,
        )
        return await loop.run_in_executor(_get_executor(), fn)

    async def re_identify_summary_async(
        self,
        db: Session,
        vault_id: str,
        summary_text: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> str:
        """Async wrapper: runs re_identify_summary in thread pool."""
        loop = loop or asyncio.get_running_loop()
        fn = partial(self.re_identify_summary, db=db, vault_id=vault_id, summary_text=summary_text)
        return await loop.run_in_executor(_get_executor(), fn)


# ── Singleton ─────────────────────────────────────────────────────────────────
presidio_deidentification_service = PresidioDeIdentificationService()
