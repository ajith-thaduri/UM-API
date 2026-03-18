"""Service for validating source data and extracting highlight terms."""

import logging
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.extraction_repository import ExtractionRepository

logger = logging.getLogger(__name__)


class SourceValidationService:
    """Service for validating source data and extracting highlight terms."""
    
    def __init__(self):
        self.case_file_repo = CaseFileRepository()
        self.extraction_repo = ExtractionRepository()
    
    def validate_file_and_page(
        self,
        db: Session,
        case_id: str,
        file_id: str,
        page_number: int
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Validate that file_id exists and page_number is within bounds.
        
        Args:
            db: Database session
            case_id: Case ID
            file_id: File ID to validate
            page_number: Page number to validate
            
        Returns:
            (is_valid, error_message, max_page) tuple
        """
        if not file_id:
            return (False, "file_id is required", None)
        
        if page_number < 1:
            return (False, f"Page number must be >= 1, got {page_number}", None)
        
        # Check if file exists
        case_file = self.case_file_repo.get_by_case_and_file_id(db, case_id, file_id)
        if not case_file:
            return (False, f"File {file_id} not found in case {case_id}", None)
        
        # Validate page number against file's page count
        if case_file.page_count and page_number > case_file.page_count:
            return (
                False,
                f"Page {page_number} exceeds maximum page {case_file.page_count}",
                case_file.page_count
            )
        
        return (True, None, case_file.page_count)
    
    def extract_highlight_term(
        self,
        description: Optional[str] = None,
        snippet: Optional[str] = None,
        entity_type: Optional[str] = None
    ) -> str:
        """
        Extract the KEY ENTITY NAME from description for precise highlighting.
        
        This function intelligently extracts ONLY the key medical entity name,
        avoiding common words that appear multiple times in the document.
        
        For diagnosis/procedure entity types, the full name is returned as-is
        to avoid matching substrings (e.g. "acute" in unrelated sentences).
        
        Examples:
        - "Started Gabapentin 300 mg TID (PO)" -> "Gabapentin"
        - "Creatinine: 1.4: mg/dL (ABNORMAL)" -> "Creatinine"
        - "Glucose (fasting): 182: mg/dL" -> "Glucose"
        - "Blood Pressure: 140/90 mmHg" -> "Blood Pressure"
        - "MRI - Lumbar Spine" -> "Lumbar Spine"
        - "X-ray - Chest" -> "Chest"
        - "Acute Hypoxic Respiratory Failure" (diagnosis) -> "Acute Hypoxic Respiratory Failure"
        
        Args:
            description: Event or entity description
            snippet: Text snippet from source document
            entity_type: Type of entity (medication, lab, timeline, diagnosis, etc.)
            
        Returns:
            Key entity name for PDF highlighting
        """
        import re
        
        if not description and not snippet:
            return ""
        
        desc = (description or "").strip()
        snip = (snippet or "").strip()
        
        # For diagnosis/procedure entities the snippet is the canonical name
        # (e.g. "Acute Hypoxic Respiratory Failure").  Return it in full so
        # find_term_bbox matches the exact multi-word phrase on the page,
        # avoiding false positives on substrings like "acute" elsewhere.
        if entity_type in ("diagnosis", "procedure"):
            full_name = (snip or desc).strip()
            if full_name:
                logger.info(
                    "[EVIDENCE] Using full %s name for highlight: '%s'",
                    entity_type, full_name[:80],
                )
                return full_name
        
        # If description is empty, fall back to snippet for the pattern matching below
        if not desc:
            desc = snip
        
        # Words to NEVER highlight (too common, appear multiple times)
        stop_words = {
            # Action words
            'started', 'stopped', 'continued', 'administered', 'given', 'prescribed',
            'ordered', 'performed', 'completed', 'scheduled', 'pending',
            # Dosage/route words
            'mg', 'mg/dl', 'mg/l', 'mmhg', 'ml', 'units', 'mcg', 'g', 'l', 'dl',
            'tid', 'bid', 'qd', 'prn', 'qid', 'hs', 'ac', 'pc',
            'po', 'iv', 'im', 'sq', 'sc', 'sl', 'pr', 'top', 'inh',
            'daily', 'twice', 'three', 'times', 'once', 'every', 'hours',
            # Status words
            'normal', 'abnormal', 'high', 'low', 'elevated', 'decreased', 'critical',
            # Common words
            'the', 'and', 'for', 'with', 'from', 'none', 'null', 'start', 'date',
            'inpatient', 'outpatient', 'patient', 'documented', 'not', 'found',
            'page', 'of', 'on', 'at', 'in', 'to', 'by', 'or', 'is', 'was', 'has',
            # Common medical document words
            'reference', 'range', 'result', 'results', 'value', 'values', 'test',
        }
        
        # PATTERN 0: Lab result in timeline - "TestName: Value: Unit"
        # For timeline events with specific values, we want to highlight the whole string
        # e.g., "Creatinine: 1.4: mg/dL (ABNORMAL)" -> "Creatinine: 1.4: mg/dL"
        lab_with_value_pattern = r'^([^:(]+:\s*[\d.]+\s*:\s*[a-zA-Z/]+)'
        lab_with_value_match = re.search(lab_with_value_pattern, desc)
        if lab_with_value_match:
            full_term = lab_with_value_match.group(1).strip()
            logger.info(f"[EVIDENCE] Extracted full lab result term: '{full_term}' from '{desc}'")
            return full_term

        # PATTERN 0.1: Simple lab result "Name: Value"
        simple_lab_pattern = r'^([^:(]+:\s*[\d.><]+(?:\s*[a-zA-Z/%]+)?)'
        simple_lab_match = re.search(simple_lab_pattern, desc)
        if simple_lab_match:
            full_term = simple_lab_match.group(1).strip()
            # Clean off any trailing colons
            full_term = full_term.rstrip(':').strip()
            logger.info(f"[EVIDENCE] Extracted simple lab result term: '{full_term}' from '{desc}'")
            return full_term
        # Examples: "Started Gabapentin 300 mg TID (PO)" -> "Gabapentin 300 mg"
        med_with_dosage_pattern = r'^(?:Started|Stopped|Prescribed|Continued|Administered|Given|Held)?\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(\d+)\s*(mg|mcg|g|ml|units|mL|MG|MCG)'
        med_match = re.match(med_with_dosage_pattern, desc, re.IGNORECASE)
        if med_match:
            med_name = med_match.group(1).strip()
            dosage = med_match.group(2).strip()
            unit = med_match.group(3).strip().lower()
            # Normalize unit
            if unit in ['mg', 'mcg', 'g', 'ml', 'units']:
                unit = unit
            # Verify medication name is not a stop word
            if med_name.lower() not in stop_words and len(med_name) > 2:
                full_term = f"{med_name} {dosage} {unit}"
                logger.info(f"[EVIDENCE] Extracted medication with dosage: '{full_term}' from '{desc}'")
                return full_term
        
        # PATTERN 2: Lab result pattern - "<TestName>: <value>" or "<TestName> (qualifier): <value>"
        # Examples: "Creatinine: 1.4: mg/dL", "Glucose (fasting): 182: mg/dL", "BUN: 26: mg/dL"
        lab_pattern = r'^([A-Za-z][A-Za-z\s]*?)(?:\s*\([^)]+\))?\s*:\s*[\d.]+'
        lab_match = re.match(lab_pattern, desc)
        if lab_match:
            test_name = lab_match.group(1).strip()
            if test_name.lower() not in stop_words and len(test_name) > 1:
                logger.info(f"[EVIDENCE] Extracted lab test name: '{test_name}' from '{desc}'")
                return test_name
        
        # PATTERN 3: Imaging/Procedure pattern with details - "<Type> - <BodyPart>"
        # Examples: "MRI - Lumbar Spine", "X-ray - Chest", "CT Scan - Abdomen"
        imaging_detail_pattern = r'^([A-Za-z\-]+(?:\s+[A-Za-z\-]+)?)\s*[-:]\s*([A-Za-z][A-Za-z\s]+)$'
        imaging_match = re.match(imaging_detail_pattern, desc)
        if imaging_match:
            # Return the body part (more specific) if it's meaningful
            body_part = imaging_match.group(2).strip()
            procedure_type = imaging_match.group(1).strip()
            if body_part.lower() not in stop_words and len(body_part) > 2:
                logger.info(f"[EVIDENCE] Extracted procedure body part: '{body_part}' from '{desc}'")
                return body_part
            elif procedure_type.lower() not in stop_words:
                logger.info(f"[EVIDENCE] Extracted procedure type: '{procedure_type}' from '{desc}'")
                return procedure_type
        
        # PATTERN 4: Vital signs pattern - known vital sign names
        vital_names = ["Blood Pressure", "Heart Rate", "Temperature", "Respiratory Rate", 
                       "Oxygen Saturation", "O2 Sat", "SpO2", "Pulse", "Weight", "Height", "BMI"]
        desc_lower = desc.lower()
        for vital in vital_names:
            if vital.lower() in desc_lower:
                logger.info(f"[EVIDENCE] Extracted vital sign: '{vital}' from '{desc}'")
                return vital
        
        # PATTERN 5: Simple medication name (no "Started" prefix)
        # Examples: "Gabapentin 300 mg", "Metformin 1000 mg"
        simple_med_pattern = r'^([A-Z][a-zA-Z]+)\s+\d+\s*(?:mg|mcg|g|ml|units)'
        simple_med_match = re.match(simple_med_pattern, desc, re.IGNORECASE)
        if simple_med_match:
            med_name = simple_med_match.group(1).strip()
            if med_name.lower() not in stop_words and len(med_name) > 2:
                logger.info(f"[EVIDENCE] Extracted simple medication: '{med_name}' from '{desc}'")
                return med_name
        
        # PATTERN 6: Procedure or Finding phrase - Extract first 2-3 capitalized words
        # Examples: "Right Total Knee Arthroplasty", "Acute Respiratory Failure"
        phrases = []
        words = desc.split()
        for word in words:
            # Clean punctuation
            clean_word = re.sub(r'[^\w\-]', '', word)
            if (clean_word and 
                clean_word.lower() not in stop_words and
                clean_word[0].isupper()):
                phrases.append(clean_word)
                if len(phrases) >= 3:
                    break
            else:
                if phrases: # Break if we hit a non-capitalized word after starting a phrase
                    break
        
        if phrases:
            result = " ".join(phrases)
            logger.info(f"[EVIDENCE] Extracted phrase fallback: '{result}' from '{desc}'")
            return result

        # Last resort: first word over 3 chars that's not a stop word
        for word in words:
            clean_word = re.sub(r'[^\w\-]', '', word)
            if clean_word.lower() not in stop_words and len(clean_word) > 3:
                logger.info(f"[EVIDENCE] Using first meaningful word: '{clean_word}' from '{desc}'")
                return clean_word
        
        logger.warning(f"[EVIDENCE] Could not extract highlight term from: '{desc}'")
        return ""
    
    def get_timeline_event_description(
        self,
        db: Session,
        case_id: str,
        event_id: str
    ) -> Optional[str]:
        """
        Get timeline event description for highlight term extraction.
        
        Args:
            db: Database session
            case_id: Case ID
            event_id: Timeline event ID
            
        Returns:
            Event description or None
        """
        try:
            extraction = self.extraction_repo.get_by_case_id(db, case_id)
            if not extraction or not extraction.timeline:
                return None
            
            timeline_events = extraction.timeline if isinstance(extraction.timeline, list) else []
            event = next(
                (e for e in timeline_events if isinstance(e, dict) and str(e.get("id", "")) == str(event_id)),
                None
            )
            
            if event:
                return event.get("description", "")
        except Exception as e:
            logger.warning(f"Could not get timeline event description: {e}")
        
        return None


# Singleton instance
source_validation_service = SourceValidationService()


