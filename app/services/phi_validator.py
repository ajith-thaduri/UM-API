"""Pre-flight PHI validator - the last line of defense before Tier 2.

This validator performs a fail-closed check on de-identified payloads before
they are sent to external LLMs (Claude). If ANY PHI is detected, the request
is BLOCKED and the system falls back to a template-based summary.

This prevents PHI leakage due to:
- Bugs in the de-identification logic
- Edge cases not caught by structured replacement
- Presidio false negatives during initial scanning

Policy:
> False positives result in safe degradation (template-based summary) rather
> than retry or override. This ensures fail-closed behavior while maintaining
> service availability.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Set

from app.core.config import settings
from app.utils.safe_logger import get_safe_logger

safe_logger = get_safe_logger(__name__)

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    safe_logger.warning("Presidio not available - PHI validation will use fallback mode")


class PHILeakageError(Exception):
    """Raised when PHI is detected in a payload that should be de-identified"""

    pass


class PHIValidator:
    """Pre-flight validator: fail-closed safety net before Tier 2"""

    def __init__(self):
        self.analyzer = None
        if PRESIDIO_AVAILABLE:
            try:
                # Initialize Presidio with high-sensitivity configuration
                nlp_config = {
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
                }
                provider = NlpEngineProvider(nlp_configuration=nlp_config)
                nlp_engine = provider.create_engine()
                self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
                safe_logger.info("PHIValidator initialized with Presidio")
            except Exception as e:
                safe_logger.error(f"Failed to initialize Presidio: {e}")

    def validate_payload(
        self,
        payload: dict,
        known_phi_values: Dict[str, str],
        case_id: str,
        allow_tokens: bool = True,
    ) -> bool:
        """
        Validate that payload contains NO PHI before sending to Tier 2.

        Args:
            payload: De-identified payload to validate
            known_phi_values: Dict of original PHI values (for exact string matching)
            case_id: Case ID for logging
            allow_tokens: If True, allow UUID tokens like [[PERSON::abc123]]

        Returns:
            True if safe (no PHI detected)

        Raises:
            PHILeakageError: If ANY PHI is detected in the payload
        """
        # Step 1: Serialize payload to text
        payload_text = self._serialize_payload(payload)

        # Step 2: Check for exact matches of known PHI values
        leaked_phi = self._check_known_phi_exact_match(payload_text, known_phi_values)
        if leaked_phi:
            safe_logger.error(
                f"Pre-flight FAILED for case {case_id}: Known PHI detected (count: {len(leaked_phi)})"
            )
            raise PHILeakageError(
                f"Known PHI values detected in payload: {len(leaked_phi)} instances"
            )

        # Step 3: Presidio scan with ultra-high threshold
        if self.analyzer:
            presidio_findings = self._presidio_scan(
                payload_text, allow_tokens=allow_tokens
            )
            if presidio_findings:
                safe_logger.error(
                    f"Pre-flight FAILED for case {case_id}: Presidio detected {len(presidio_findings)} entities"
                )
                raise PHILeakageError(
                    f"Presidio detected {len(presidio_findings)} potential PHI entities"
                )

        # Payload is safe
        safe_logger.info(f"Pre-flight PASSED for case {case_id}")
        return True

    def _serialize_payload(self, payload: dict) -> str:
        """Convert payload to text for scanning"""
        try:
            # Use JSON serialization for structured data
            return json.dumps(payload, indent=2, default=str)
        except Exception as e:
            safe_logger.warning(f"Failed to serialize payload: {e}")
            return str(payload)

    def _check_known_phi_exact_match(
        self, text: str, known_phi_values: Dict[str, str]
    ) -> List[str]:
        """
        Check for exact string matches of known PHI values.

        This catches cases where de-identification failed to replace a value.
        """
        leaked = []
        for phi_value, phi_type in known_phi_values.items():
            if not phi_value or not isinstance(phi_value, str):
                continue

            # Case-insensitive exact word match
            # Use word boundaries to avoid false positives
            pattern = r"\b" + re.escape(phi_value) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                leaked.append(f"{phi_type}: {phi_value[:10]}...")
                safe_logger.error(f"Known PHI leaked: {phi_type} (partial: {phi_value[:10]}...)")

        return leaked

    def _presidio_scan(
        self, text: str, allow_tokens: bool = True
    ) -> List[Dict]:
        """
        Scan text with Presidio using ultra-high threshold.

        Uses threshold of 0.90 (vs 0.70 for initial de-identification)
        to catch any remaining PHI while minimizing false positives.
        """
        if not self.analyzer:
            return []

        # Get threshold from config
        threshold = getattr(settings, "PRESIDIO_PREFLIGHT_THRESHOLD", 0.9)
        entities = getattr(
            settings,
            "PRESIDIO_ENTITIES",
            ["PERSON", "PHONE_NUMBER", "US_SSN", "EMAIL_ADDRESS", "LOCATION", "ORGANIZATION"],
        )

        try:
            results = self.analyzer.analyze(
                text=text,
                entities=entities,
                language="en",
                score_threshold=threshold,
            )

            # Filter out intentional tokens if allow_tokens=True
            if allow_tokens:
                results = self._filter_tokens(results, text)

            # Convert to dict for logging
            findings = []
            for result in results:
                findings.append(
                    {
                        "entity_type": result.entity_type,
                        "score": result.score,
                        "start": result.start,
                        "end": result.end,
                    }
                )

            return findings

        except Exception as e:
            safe_logger.error(f"Presidio scan failed: {e}")
            # Fail-closed: if scan fails, assume PHI present
            return [{"entity_type": "SCAN_ERROR", "score": 1.0}]

    def _filter_tokens(self, results: List, text: str) -> List:
        """
        Filter out UUID tokens from Presidio results.

        Tokens like [[PERSON::a94f2c3b12ef]] are intentional and should not
        be flagged as PHI.
        """
        # Token pattern: [[TYPE::uuid12]]
        token_pattern = r"\[\[[A-Z_]+::[a-f0-9]{8,16}\]\]"

        filtered = []
        for result in results:
            # Extract the detected text
            start, end = result.start, result.end
            detected_text = text[start:end]

            # Check if it's a token
            if re.match(token_pattern, detected_text):
                continue  # Skip tokens

            filtered.append(result)

        return filtered


# Singleton instance
phi_validator = PHIValidator()
