"""Timeline construction service with hybrid RAG support"""

import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import logging
from sqlalchemy.orm import Session

from app.models.document_chunk import SectionType
from app.utils.date_utils import (
    normalize_date_format,
    parse_date_for_sort,
    get_date_from_dict
)
from app.utils.event_validator import (
    validate_event_consistency,
    filter_events_without_sources,
    validate_event_descriptions,
    deduplicate_events
)
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


class TimelineService:
    """Service for constructing chronological clinical timelines with hybrid RAG"""

    def build_timeline(
        self,
        extracted_data: Dict,
        raw_text: str,
        db: Optional[Session] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        Build two-level chronological timeline from extracted clinical data
        - Summary: Major events only (admissions, discharges, major procedures, diagnoses, critical findings)
        - Detailed: All events including routine labs, vitals, medication changes
        
        Uses hybrid approach: extracted_data + RAG supplement for date-rich chunks

        Args:
            extracted_data: Extracted clinical information
            raw_text: Original medical record text
            db: Database session (for RAG supplement)
            case_id: Case ID (for RAG supplement)
            user_id: User ID (for RAG supplement)

        Returns:
            Dict with 'summary' and 'detailed' keys, each containing List of timeline events sorted chronologically
        """
        timeline_events = []

        # Primary: Build from extracted_data
        # Extract admission/discharge/transfer events FIRST (needed for context)
        admission_events = self._extract_admission_discharge_events(extracted_data)
        medication_events = self._extract_medication_events(extracted_data)
        procedure_events = self._extract_procedure_events(extracted_data)
        vital_events = self._extract_vital_events(extracted_data)
        lab_events = self._extract_lab_events(extracted_data)
        imaging_events = self._extract_imaging_events(extracted_data)
        diagnosis_events = self._extract_diagnosis_events(extracted_data)
        social_factor_events = self._extract_social_factor_events(extracted_data)
        therapy_events = self._extract_therapy_events(extracted_data)
        
        # Add events in order of importance (admission/discharge first for context)
        timeline_events.extend(admission_events)
        timeline_events.extend(medication_events)
        timeline_events.extend(procedure_events)
        timeline_events.extend(vital_events)
        timeline_events.extend(lab_events)
        timeline_events.extend(imaging_events)
        timeline_events.extend(diagnosis_events)
        timeline_events.extend(social_factor_events)
        timeline_events.extend(therapy_events)
        
        # Log extraction results for debugging
        logger.info(f"Timeline extraction: {len(admission_events)} admission/discharge, {len(medication_events)} medication, {len(procedure_events)} procedure, {len(vital_events)} vital, {len(lab_events)} lab, {len(imaging_events)} imaging, {len(diagnosis_events)} diagnosis, {len(social_factor_events)} social factor, {len(therapy_events)} therapy events")
        if len(timeline_events) == 0:
            # Log why no events were extracted
            logger.warning(f"No timeline events extracted. Extracted data keys: {list(extracted_data.keys()) if isinstance(extracted_data, dict) else 'not a dict'}")
            if isinstance(extracted_data, dict):
                logger.warning(f"Medications: {len(extracted_data.get('medications', []))}, Labs: {len(extracted_data.get('labs', []))}, Vitals: {len(extracted_data.get('vitals', []))}, Procedures: {len(extracted_data.get('procedures', []))}, Imaging: {len(extracted_data.get('imaging', []))}, Diagnoses: {len(extracted_data.get('diagnoses', []))}")
                # Sample first medication to check for dates
                if extracted_data.get('medications'):
                    sample_med = extracted_data['medications'][0]
                    logger.warning(f"Sample medication keys: {list(sample_med.keys()) if isinstance(sample_med, dict) else 'not a dict'}, has date: {bool(self._get_date(sample_med)) if isinstance(sample_med, dict) else False}")

        # Supplement: Use RAG to find additional date-related events
        # Note: This is called from asyncio.to_thread, so we can't use await directly
        # We'll skip RAG supplement in this context to avoid async complexity
        # RAG supplement can be added as a separate async step if needed
        if db and case_id and user_id:
            try:
                # Skip async RAG supplement when called from thread pool
                # This is a trade-off for performance - RAG supplement is optional
                logger.debug("Skipping RAG supplement in synchronous context")
            except Exception as e:
                logger.warning(f"RAG supplement skipped: {e}")

        # Validate event consistency before filtering (ensures data quality)
        timeline_events = self._validate_event_consistency(timeline_events)
        
        # Filter out events without source references (CRITICAL: Audit requirement)
        timeline_events = self._filter_events_without_sources(timeline_events)

        # Sort events chronologically
        timeline_events = self._sort_timeline(timeline_events)

        # Deduplicate similar events
        timeline_events = self._deduplicate_events(timeline_events)

        # Validate event descriptions (remove interpretation language)
        timeline_events = self._validate_event_descriptions(timeline_events)

        # Split into summary and detailed timelines
        summary_timeline = self._extract_summary_events(timeline_events)
        detailed_timeline = timeline_events  # All events
        
        logger.info(f"Timeline split: {len(summary_timeline)} summary events, {len(detailed_timeline)} detailed events for case {case_id}")
        
        return {
            "summary": summary_timeline,
            "detailed": detailed_timeline
        }

    def _get_date(self, item: Dict, keys: List[str] = None) -> Optional[str]:
        """Helper to get date from item using multiple possible keys"""
        if not keys:
            keys = ["date", "Date", "start_date", "startDate", "time", "timestamp"]
        
        for key in keys:
            if isinstance(item, dict) and item.get(key):
                date_val = item[key]
                # Normalize the date if it's a valid string
                if isinstance(date_val, str) and date_val.strip():
                    normalized = self._normalize_date_format(date_val.strip())
                    if normalized:
                        return normalized
                elif date_val:  # Non-empty non-string value
                    return str(date_val).strip()
        return None

    def _normalize_date_format(self, date_str: str) -> Optional[str]:
        """
        Normalize date string to MM/DD/YYYY format consistently.
        Handles various input formats and converts them to standard format.
        """
        if not date_str or not isinstance(date_str, str):
            return None
        
        date_str = date_str.strip()
        if not date_str or date_str.lower() in ["null", "none", "n/a", ""]:
            return None
        
        # Try to parse various date formats
        date_formats = [
            "%m/%d/%Y",  # MM/DD/YYYY
            "%m-%d-%Y",  # MM-DD-YYYY
            "%Y-%m-%d",  # YYYY-MM-DD (ISO format)
            "%m/%d/%y",  # MM/DD/YY (2-digit year)
            "%m-%d-%y",  # MM-DD-YY
            "%d/%m/%Y",  # DD/MM/YYYY (European format)
            "%d-%m-%Y",  # DD-MM-YYYY
            "%B %d, %Y",  # January 12, 2025
            "%b %d, %Y",  # Jan 12, 2025
            "%d %B %Y",  # 12 January 2025
            "%d %b %Y",  # 12 Jan 2025
            "%Y/%m/%d",  # YYYY/MM/DD
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Convert 2-digit year to 4-digit (assume 2000s for years < 50, 1900s for >= 50)
                if "%y" in fmt:
                    if dt.year < 100:
                        if dt.year < 50:
                            dt = dt.replace(year=2000 + dt.year)
                        else:
                            dt = dt.replace(year=1900 + dt.year)
                return dt.strftime("%m/%d/%Y")
            except (ValueError, TypeError):
                continue
        
        # Try regex-based parsing for non-standard formats
        import re
        # Pattern: MM/DD/YYYY or MM-DD-YYYY or YYYY-MM-DD
        match = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", date_str)
        if match:
            month, day, year = match.groups()
            try:
                month_int = int(month)
                day_int = int(day)
                year_int = int(year)
                
                # Handle 2-digit year
                if year_int < 100:
                    year_int = 2000 + year_int if year_int < 50 else 1900 + year_int
                
                # Validate month and day
                if 1 <= month_int <= 12 and 1 <= day_int <= 31:
                    dt = datetime(year_int, month_int, day_int)
                    return dt.strftime("%m/%d/%Y")
            except (ValueError, TypeError):
                pass
        
        # If all parsing fails, return None (don't use invalid dates)
        logger.debug(f"Could not parse date format: {date_str}")
        return None

    def _parse_date_for_sort(self, date_str: Optional[str]) -> datetime:
        """Parse date string for sorting purposes. Returns datetime.min if invalid."""
        if not date_str:
            return datetime.min
        
        # First try to normalize the date format
        normalized = self._normalize_date_format(date_str)
        if normalized:
            date_str = normalized
        
        # Try standard formats
        formats = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        
        # If all parsing fails, return min date (will sort to beginning)
        logger.debug(f"Could not parse date for sorting: {date_str}")
        return datetime.min

    def _extract_medication_events(self, extracted_data: Dict) -> List[Dict]:
        """
        Extract medication events including:
        - Start dates
        - Stop dates
        - Dose changes (when same medication has different dosage)
        - Route changes (when same medication has different route)
        
        Each event MUST include date and source (audit requirement).
        MUST NOT infer rationale for changes - only document factual changes.
        """
        events = []
        medications = extracted_data.get("medications", [])
        
        if not medications:
            return events
        
        # Group medications by name (normalized) to detect changes
        med_by_name = {}
        for med in medications:
            name = med.get("name", "").strip()
            if name:
                # Normalize name for comparison (case-insensitive, trimmed)
                name_key = name.lower().strip()
                if name_key not in med_by_name:
                    med_by_name[name_key] = []
                med_by_name[name_key].append(med)
        
        # Process each medication group
        for med_name_key, med_list in med_by_name.items():
            # Sort by start_date to track chronological changes
            # If no start_date, use date field or put at end
            sorted_meds = sorted(
                med_list,
                key=lambda m: self._parse_date_for_sort(
                    self._get_date(m, ["start_date", "startDate", "date", "started"])
                )
            )
            
            prev_med = None
            for med in sorted_meds:
                med_name = med.get("name", "Medication")
                start_date = self._get_date(med, ["start_date", "startDate", "date", "started"])
                
                # Create start event (existing functionality - preserve)
                if start_date:
                    dosage = med.get("dosage", "")
                    frequency = med.get("frequency", "")
                    route = med.get("route", "")
                    
                    # Build description with available info
                    desc_parts = [f"Started {med_name}"]
                    if dosage:
                        desc_parts.append(dosage)
                    if frequency:
                        desc_parts.append(frequency)
                    if route:
                        desc_parts.append(f"({route})")
                    
                    events.append({
                        "id": str(uuid.uuid4()),
                        "date": start_date,
                        "event_type": "medication_started",
                        "description": " ".join(desc_parts).strip(),
                        "source": "medications",
                        "details": med,
                        "source_file": med.get("source_file"),
                        "source_page": med.get("source_page")
                    })
            
                # Detect changes compared to previous medication entry (NEW functionality)
                if prev_med:
                    prev_name = prev_med.get("name", "").strip()
                    curr_name = med_name.strip()
                    
                    # Only detect changes if it's the same medication
                    if prev_name.lower() == curr_name.lower():
                        change_date = start_date or self._get_date(med, ["date"])
                        
                        # Detect dose change
                        prev_dosage = (prev_med.get("dosage") or "").strip()
                        curr_dosage = (med.get("dosage") or "").strip()
                        prev_frequency = (prev_med.get("frequency") or "").strip()
                        curr_frequency = (med.get("frequency") or "").strip()
                        
                        # Check if dosage or frequency changed
                        dosage_changed = (
                            prev_dosage and curr_dosage and 
                            prev_dosage.lower() != curr_dosage.lower()
                        )
                        frequency_changed = (
                            prev_frequency and curr_frequency and 
                            prev_frequency.lower() != curr_frequency.lower()
                        )
                        
                        if (dosage_changed or frequency_changed) and change_date:
                            # Build factual description of change (no rationale)
                            change_desc_parts = []
                            if dosage_changed:
                                change_desc_parts.append(f"Dosage changed to {curr_dosage}")
                            if frequency_changed and not dosage_changed:
                                change_desc_parts.append(f"Frequency changed to {curr_frequency}")
                            elif frequency_changed:
                                change_desc_parts.append(f"Frequency changed to {curr_frequency}")
                            
                            if change_desc_parts:
                                events.append({
                                    "id": str(uuid.uuid4()),
                                    "date": change_date,
                                    "event_type": "medication_changed",
                                    "description": f"{med_name}: {'; '.join(change_desc_parts)}".strip(),
                                    "source": "medications",
                                    "details": med,
                                    "source_file": med.get("source_file"),
                                    "source_page": med.get("source_page")
                                })
                        
                        # Detect route change
                        prev_route = (prev_med.get("route") or "").strip().lower()
                        curr_route = (med.get("route") or "").strip().lower()
                        
                        if prev_route and curr_route and prev_route != curr_route and change_date:
                            # Check if this is an IV→PO transition (evidence signal)
                            is_iv_prev = any(iv_term in prev_route for iv_term in ["iv", "intravenous", "i.v.", "i v"])
                            is_po_curr = any(po_term in curr_route for po_term in ["po", "oral", "by mouth", "p.o.", "p o"])
                            
                            event = {
                                "id": str(uuid.uuid4()),
                                "date": change_date,
                                "event_type": "medication_changed",
                                "description": f"{med_name}: Route changed to {med.get('route')}".strip(),
                                "source": "medications",
                                "details": med,
                                "source_file": med.get("source_file"),
                                "source_page": med.get("source_page")
                            }
                            
                            # Tag as evidence signal if IV→PO transition
                            if is_iv_prev and is_po_curr:
                                event["is_evidence_signal"] = True
                                event["evidence_signal_type"] = "iv_to_po"
                            
                            events.append(event)
                
                # Store current medication as previous for next iteration
                prev_med = med
                
                # Create stop event (existing functionality - preserve)
            end_date = self._get_date(med, ["end_date", "endDate", "stopped"])
            if end_date:
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": end_date,
                    "event_type": "medication_ended",
                        "description": f"Stopped {med_name}",
                    "source": "medications",
                    "details": med,
                    "source_file": med.get("source_file"),
                    "source_page": med.get("source_page")
                })
        
        return events

    def categorize_medications(
        self,
        medications: List[Dict],
        timeline_events: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        Categorize medications into exactly three buckets:
        1. admission_home: Medications before/on admission or home medications
        2. inpatient: Medications started during inpatient stay
        3. discharge: Medications prescribed at discharge
        
        Each medication MUST appear in exactly one category with date context.
        
        Args:
            medications: List of medication dictionaries
            timeline_events: List of timeline events to find admission/discharge dates
            
        Returns:
            Dict with keys: "admission_home", "inpatient", "discharge"
            Each contains list of medications with "category" and "category_date" fields
        """
        # Find admission and discharge dates from timeline events
        admission_date = None
        discharge_date = None
        
        for event in timeline_events:
            event_type = event.get("event_type", "")
            if event_type == "admission":
                admission_date = event.get("date")
            elif event_type == "discharge":
                discharge_date = event.get("date")
        
        # Helper to parse date string to datetime
        def parse_date(date_str: Optional[str]) -> Optional[datetime]:
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, "%m/%d/%Y")
            except:
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    return None
        
        admission_dt = parse_date(admission_date) if admission_date else None
        discharge_dt = parse_date(discharge_date) if discharge_date else None
        
        categorized = {
            "admission_home": [],
            "inpatient": [],
            "discharge": []
        }
        
        for med in medications:
            # Create a copy to avoid modifying original
            med_copy = med.copy()
            
            start_date = self._get_date(med, ["start_date", "startDate", "date"])
            start_dt = parse_date(start_date) if start_date else None
            
            # Check if medication is mentioned in discharge context
            source_file = (med.get("source_file") or "").lower()
            description = (med.get("description", "") + " " + (med.get("indication") or "")).lower()
            context_hint = (med.get("context") or "").lower()
            
            is_discharge_med = (
                "discharge" in source_file or
                "discharge" in description or
                context_hint == "discharge" or
                (discharge_dt and start_dt and start_dt.date() == discharge_dt.date())
            )
            
            # Check if medication is explicitly a home/continuing medication
            is_home_med = (
                "home" in description or
                "continuing" in description or
                "continue" in description or
                context_hint == "admission_home" or
                context_hint == "home"
            )
            
            # Categorization logic (must assign to exactly one bucket)
            if is_discharge_med and discharge_dt:
                # Discharge medication
                med_copy["category"] = "discharge"
                med_copy["category_date"] = discharge_date
                categorized["discharge"].append(med_copy)
            elif admission_dt and start_dt:
                # We have both admission date and medication start date
                if start_dt < admission_dt:
                    # Started before admission - admission/home
                    med_copy["category"] = "admission_home"
                    med_copy["category_date"] = admission_date
                    categorized["admission_home"].append(med_copy)
                elif start_dt.date() == admission_dt.date():
                    # Started on admission date
                    if is_home_med:
                        # Explicitly marked as home/continuing
                        med_copy["category"] = "admission_home"
                        med_copy["category_date"] = admission_date
                        categorized["admission_home"].append(med_copy)
                    elif discharge_dt and start_dt < discharge_dt:
                        # Started on admission but continued during stay
                        med_copy["category"] = "inpatient"
                        med_copy["category_date"] = admission_date
                        categorized["inpatient"].append(med_copy)
                    else:
                        # Started on admission, no discharge date
                        med_copy["category"] = "inpatient"
                        med_copy["category_date"] = admission_date
                        categorized["inpatient"].append(med_copy)
                elif discharge_dt and start_dt < discharge_dt:
                    # Started during inpatient stay (after admission, before discharge)
                    med_copy["category"] = "inpatient"
                    med_copy["category_date"] = start_date
                    categorized["inpatient"].append(med_copy)
                else:
                    # Started after discharge or on discharge date
                    med_copy["category"] = "discharge"
                    med_copy["category_date"] = start_date or discharge_date
                    categorized["discharge"].append(med_copy)
            elif admission_dt and not start_dt:
                # Have admission date but no medication start date
                if is_discharge_med:
                    med_copy["category"] = "discharge"
                    med_copy["category_date"] = discharge_date
                    categorized["discharge"].append(med_copy)
                elif is_home_med:
                    med_copy["category"] = "admission_home"
                    med_copy["category_date"] = admission_date
                    categorized["admission_home"].append(med_copy)
                else:
                    # Default: if we have admission date but no start date, assume admission/home
                    med_copy["category"] = "admission_home"
                    med_copy["category_date"] = admission_date
                    categorized["admission_home"].append(med_copy)
            elif not admission_dt and not discharge_dt:
                # No admission or discharge dates available
                # Use heuristics based on context
                if is_discharge_med:
                    med_copy["category"] = "discharge"
                    med_copy["category_date"] = None
                    categorized["discharge"].append(med_copy)
                elif is_home_med:
                    med_copy["category"] = "admission_home"
                    med_copy["category_date"] = None
                    categorized["admission_home"].append(med_copy)
                else:
                    # Default to admission_home if unclear
                    med_copy["category"] = "admission_home"
                    med_copy["category_date"] = None
                    categorized["admission_home"].append(med_copy)
            else:
                # Edge case: have dates but logic didn't catch it
                # Default to admission_home
                med_copy["category"] = "admission_home"
                med_copy["category_date"] = admission_date
                categorized["admission_home"].append(med_copy)
        
        logger.info(
            f"Medication categorization: {len(categorized['admission_home'])} admission/home, "
            f"{len(categorized['inpatient'])} inpatient, {len(categorized['discharge'])} discharge"
        )
        
        return categorized

    def _extract_admission_discharge_events(self, extracted_data: Dict) -> List[Dict]:
        """
        Extract admission, discharge, transfer, and emergency visit events.
        These are critical for timeline context and medication categorization.
        """
        events = []
        
        # Check for encounter/admission/discharge info in extracted_data
        # Look in various places where this info might be stored
        encounter_date = None
        admission_date = None
        discharge_date = None
        
        # Check top-level extracted_data fields
        if isinstance(extracted_data, dict):
            # Try common field names
            encounter_date = extracted_data.get("encounter_date") or extracted_data.get("visit_date")
            admission_date = extracted_data.get("admission_date") or extracted_data.get("admit_date")
            discharge_date = extracted_data.get("discharge_date") or extracted_data.get("discharged_date")
            
            # Check in patient_info if it exists
            patient_info = extracted_data.get("patient_info") or extracted_data.get("patient_demographics")
            if isinstance(patient_info, dict):
                if not encounter_date:
                    encounter_date = patient_info.get("encounter_date") or patient_info.get("visit_date")
                if not admission_date:
                    admission_date = patient_info.get("admission_date") or patient_info.get("admit_date")
                if not discharge_date:
                    discharge_date = patient_info.get("discharge_date") or patient_info.get("discharged_date")
            
            # Check in request_metadata
            request_metadata = extracted_data.get("request_metadata")
            if isinstance(request_metadata, dict):
                if not admission_date:
                    admission_date = request_metadata.get("admission_date") or request_metadata.get("admit_date")
                if not discharge_date:
                    discharge_date = request_metadata.get("discharge_date")
        
        # Extract admission event
        if admission_date:
            normalized_date = self._normalize_date_format(str(admission_date))
            if normalized_date:
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": normalized_date,
                    "event_type": "admission",
                    "description": "Patient admitted",
                    "source": "clinical_data",
                    "details": {"admission_date": normalized_date},
                    "source_file": extracted_data.get("source_file"),
                    "source_page": extracted_data.get("source_page")
                })
        
        # Extract discharge event
        if discharge_date:
            normalized_date = self._normalize_date_format(str(discharge_date))
            if normalized_date:
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": normalized_date,
                    "event_type": "discharge",
                    "description": "Patient discharged",
                    "source": "clinical_data",
                    "details": {"discharge_date": normalized_date},
                    "source_file": extracted_data.get("source_file"),
                    "source_page": extracted_data.get("source_page")
                })
        
        # Extract encounter/visit event if different from admission
        if encounter_date and encounter_date != admission_date and encounter_date != discharge_date:
            normalized_date = self._normalize_date_format(str(encounter_date))
            if normalized_date:
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": normalized_date,
                    "event_type": "emergency_visit",  # Default to emergency_visit for encounters
                    "description": "Patient visit/encounter",
                    "source": "clinical_data",
                    "details": {"encounter_date": normalized_date},
                    "source_file": extracted_data.get("source_file"),
                    "source_page": extracted_data.get("source_page")
                })
        
        # Also check if procedures indicate admission/discharge context
        # (This helps capture events that might not be explicitly extracted)
        procedures = extracted_data.get("procedures", [])
        for proc in procedures:
            if isinstance(proc, dict):
                proc_name = (proc.get("name") or "").lower()
                # Look for admission/discharge procedures
                if "admission" in proc_name or "admit" in proc_name:
                    proc_date = self._get_date(proc)
                    if proc_date and not any(e.get("event_type") == "admission" and e.get("date") == proc_date for e in events):
                        events.append({
                            "id": str(uuid.uuid4()),
                            "date": proc_date,
                            "event_type": "admission",
                            "description": f"Admission: {proc.get('name', 'Admission')}",
                            "source": "procedures",
                            "details": proc,
                            "source_file": proc.get("source_file"),
                            "source_page": proc.get("source_page")
                        })
                elif "discharge" in proc_name:
                    proc_date = self._get_date(proc)
                    if proc_date and not any(e.get("event_type") == "discharge" and e.get("date") == proc_date for e in events):
                        events.append({
                            "id": str(uuid.uuid4()),
                            "date": proc_date,
                            "event_type": "discharge",
                            "description": f"Discharge: {proc.get('name', 'Discharge')}",
                            "source": "procedures",
                            "details": proc,
                            "source_file": proc.get("source_file"),
                            "source_page": proc.get("source_page")
                        })
        
        return events

    def _extract_procedure_events(self, extracted_data: Dict) -> List[Dict]:
        """Extract procedure events"""
        events = []
        for proc in extracted_data.get("procedures", []):
            if not isinstance(proc, dict):
                continue
            
            # Skip admission/discharge procedures (handled separately)
            proc_name = (proc.get("name") or "").lower()
            if "admission" in proc_name or "admit" in proc_name or "discharge" in proc_name:
                continue
            
            date = self._get_date(proc, ["date", "Date", "performed_on", "procedure_date", "performed_date"])
            if date:
                proc_description = proc.get("name", "Procedure")
                # Add location if available
                location = proc.get("location")
                if location:
                    proc_description = f"{proc_description} ({location})"
                
                event = {
                    "id": str(uuid.uuid4()),
                    "date": date,
                    "event_type": "procedure",
                    "description": proc_description,
                    "source": "procedures",
                    "details": proc,
                    "source_file": proc.get("source_file"),
                    "source_page": proc.get("source_page")
                }
                
                # Check if this is an ambulation/mobility procedure (evidence signal)
                proc_notes_lower = (proc.get("notes") or "").lower()
                proc_findings_lower = (proc.get("findings") or "").lower()
                combined_text = f"{proc_name} {proc_notes_lower} {proc_findings_lower}"
                
                ambulation_keywords = [
                    "ambulation", "ambulate", "walking", "walk", "mobility", "mobilization",
                    "physical therapy", "pt", "out of bed", "oob", "up ad lib", "up with assistance",
                    "assist to chair", "sitting", "standing", "transfer", "gait", "up to chair"
                ]
                
                if any(keyword in combined_text for keyword in ambulation_keywords):
                    event["is_evidence_signal"] = True
                    event["evidence_signal_type"] = "ambulation"
                
                events.append(event)
        return events

    def _extract_vital_events(self, extracted_data: Dict) -> List[Dict]:
        """Extract vital sign events"""
        events = []
        for vital in extracted_data.get("vitals", []):
            if not isinstance(vital, dict):
                continue
            
            date = self._get_date(vital, ["date", "Date", "recorded_date", "time", "timestamp"])
            if date:
                vital_type = vital.get("type", "Vital")
                value = vital.get("value", "")
                unit = vital.get("unit", "")
                
                # Build description
                desc_parts = [vital_type]
                if value:
                    desc_parts.append(value)
                if unit:
                    desc_parts.append(unit)
                
                event = {
                    "id": str(uuid.uuid4()),
                    "date": date,
                    "event_type": "vital_recorded",
                    "description": ": ".join(desc_parts).strip() if len(desc_parts) > 1 else desc_parts[0],
                    "source": "vitals",
                    "details": vital,
                    "source_file": vital.get("source_file"),
                    "source_page": vital.get("source_page")
                }
                
                # Check if this indicates room air (oxygen discontinuation) - evidence signal
                vital_type_lower = vital_type.lower()
                vital_notes_lower = (vital.get("notes") or "").lower()
                vital_value_lower = str(value).lower()
                vital_unit_lower = str(unit).lower()
                combined_text = f"{vital_type_lower} {vital_notes_lower} {vital_value_lower} {vital_unit_lower}".lower()
                
                room_air_keywords = ["room air", "ra", "no oxygen", "off oxygen", "discontinued oxygen",
                                    "o2 discontinued", "oxygen discontinued", "no o2", "off o2"]
                
                if any(keyword in combined_text for keyword in room_air_keywords):
                    event["is_evidence_signal"] = True
                    event["evidence_signal_type"] = "room_air"
                
                events.append(event)
        return events

    def compute_vitals_per_day_ranges(
        self,
        vitals: List[Dict],
        timeline_events: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        Compute per-day ranges for vitals (BP, HR, SpO₂, Temperature) for each hospital day.
        
        For each hospital day, computes min/max for:
        - Blood Pressure (systolic/diastolic separately)
        - Heart Rate
        - SpO₂ (Oxygen Saturation)
        - Temperature
        - CRP (C-reactive Protein)
        
        Args:
            vitals: List of vital sign dictionaries with type, value, unit, date
            timeline_events: List of timeline events to find admission/discharge dates
            
        Returns:
            Dict with keys being dates (MM/DD/YYYY) and values being dicts with:
            - date: Date string
            - blood_pressure: {"min": "sys/dias", "max": "sys/dias"} or "Range not available"
            - heart_rate: {"min": value, "max": value} or "Range not available"
            - spO2: {"min": value, "max": value} or "Range not available"
            - temperature: {"min": value, "max": value} or "Range not available"
            - crp: {"min": value, "max": value} or "Range not available"
        """
        # Find admission and discharge dates from timeline
        admission_date = None
        discharge_date = None
        
        for event in timeline_events:
            event_type = event.get("event_type", "")
            if event_type == "admission":
                admission_date = event.get("date")
            elif event_type == "discharge":
                discharge_date = event.get("date")
        
        # Helper to parse date string to datetime
        def parse_date(date_str: Optional[str]) -> Optional[datetime]:
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, "%m/%d/%Y")
            except:
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    return None
        
        # Helper to normalize date to MM/DD/YYYY
        def normalize_date(date_str: Optional[str]) -> Optional[str]:
            if not date_str:
                return None
            dt = parse_date(date_str)
            if dt:
                return dt.strftime("%m/%d/%Y")
            return date_str
        
        admission_dt = parse_date(admission_date) if admission_date else None
        discharge_dt = parse_date(discharge_date) if discharge_date else None
        
        # Group vitals by date
        vitals_by_date: Dict[str, List[Dict]] = {}
        for vital in vitals:
            vital_date = self._get_date(vital)
            if vital_date:
                normalized_date = normalize_date(vital_date)
                if normalized_date:
                    if normalized_date not in vitals_by_date:
                        vitals_by_date[normalized_date] = []
                    vitals_by_date[normalized_date].append(vital)
        
        # Filter to only hospital days (between admission and discharge)
        if admission_dt:
            hospital_dates = []
            current_date = admission_dt.date()
            end_date = discharge_dt.date() if discharge_dt else (datetime.now().date() + timedelta(days=30))
            
            while current_date <= end_date:
                date_str = current_date.strftime("%m/%d/%Y")
                hospital_dates.append(date_str)
                current_date += timedelta(days=1)
            
            # Only process dates that have vitals or are within hospital stay
            dates_to_process = set(hospital_dates) | set(vitals_by_date.keys())
            if discharge_dt:
                dates_to_process = {d for d in dates_to_process if parse_date(d) and parse_date(d).date() <= discharge_dt.date()}
        else:
            # If no admission date, use all dates with vitals
            dates_to_process = set(vitals_by_date.keys())
        
        # Compute ranges for each date
        per_day_ranges = {}
        for date_str in sorted(dates_to_process):
            date_vitals = vitals_by_date.get(date_str, [])
            
            # Initialize ranges for this date
            bp_systolic_values = []
            bp_diastolic_values = []
            hr_values = []
            spo2_values = []
            temp_values = []
            crp_values = []
            
            # Parse vitals by type
            for vital in date_vitals:
                vital_type = (vital.get("type") or "").lower()
                value_str = str(vital.get("value") or "").strip()
                unit = (vital.get("unit") or "").lower()
                
                # Blood Pressure: Look for "systolic/diastolic" format (e.g., "120/80")
                if "blood pressure" in vital_type or "bp" in vital_type:
                    # Try to parse "120/80" format
                    if "/" in value_str:
                        parts = value_str.split("/")
                        if len(parts) == 2:
                            try:
                                sys = float(parts[0].strip())
                                dias = float(parts[1].strip())
                                bp_systolic_values.append(sys)
                                bp_diastolic_values.append(dias)
                            except:
                                pass
                    # Also handle separate systolic/diastolic entries
                    elif "systolic" in vital_type:
                        try:
                            bp_systolic_values.append(float(value_str))
                        except:
                            pass
                    elif "diastolic" in vital_type:
                        try:
                            bp_diastolic_values.append(float(value_str))
                        except:
                            pass
                
                # Heart Rate: Look for HR, pulse, heart rate
                elif "heart rate" in vital_type or "hr" in vital_type or "pulse" in vital_type:
                    try:
                        hr_values.append(float(value_str))
                    except:
                        pass
                
                # SpO₂: Look for spo2, o2 sat, oxygen saturation
                elif "spo2" in vital_type or "o2 sat" in vital_type or "oxygen saturation" in vital_type or "spo₂" in vital_type:
                    try:
                        spo2_values.append(float(value_str))
                    except:
                        pass
                
                # Temperature: Look for temp, temperature
                elif "temperature" in vital_type or "temp" in vital_type:
                    # Handle Fahrenheit (convert to numeric)
                    try:
                        temp_val = float(value_str.replace("°F", "").replace("°C", "").strip())
                        # If unit is Celsius, convert to Fahrenheit for consistency (optional)
                        if "c" in unit and temp_val < 100:  # Likely Celsius if < 100
                            temp_val = (temp_val * 9/5) + 32
                        temp_values.append(temp_val)
                    except:
                        pass
                
                # CRP: Look for crp, c-reactive protein
                elif "crp" in vital_type or "c-reactive" in vital_type or "c reactive" in vital_type:
                    try:
                        crp_values.append(float(value_str))
                    except:
                        pass
            
            # Compute ranges
            bp_range = "Range not available"
            if bp_systolic_values and bp_diastolic_values:
                min_sys = min(bp_systolic_values)
                max_sys = max(bp_systolic_values)
                min_dias = min(bp_diastolic_values)
                max_dias = max(bp_diastolic_values)
                bp_range = {
                    "min": f"{int(min_sys)}/{int(min_dias)}",
                    "max": f"{int(max_sys)}/{int(max_dias)}"
                }
            
            hr_range = "Range not available"
            if len(hr_values) >= 2:
                hr_range = {
                    "min": int(min(hr_values)),
                    "max": int(max(hr_values))
                }
            elif len(hr_values) == 1:
                hr_range = {"min": int(hr_values[0]), "max": int(hr_values[0])}
            
            spo2_range = "Range not available"
            if len(spo2_values) >= 2:
                spo2_range = {
                    "min": int(min(spo2_values)),
                    "max": int(max(spo2_values))
                }
            elif len(spo2_values) == 1:
                spo2_range = {"min": int(spo2_values[0]), "max": int(spo2_values[0])}
            
            temp_range = "Range not available"
            if len(temp_values) >= 2:
                temp_range = {
                    "min": round(min(temp_values), 1),
                    "max": round(max(temp_values), 1)
                }
            elif len(temp_values) == 1:
                temp_range = {"min": round(temp_values[0], 1), "max": round(temp_values[0], 1)}
            
            crp_range = "Range not available"
            if len(crp_values) >= 2:
                crp_range = {
                    "min": round(min(crp_values), 1),
                    "max": round(max(crp_values), 1)
                }
            elif len(crp_values) == 1:
                crp_range = {"min": round(crp_values[0], 1), "max": round(crp_values[0], 1)}
            
            per_day_ranges[date_str] = {
                "date": date_str,
                "blood_pressure": bp_range,
                "heart_rate": hr_range,
                "spO2": spo2_range,
                "temperature": temp_range,
                "crp": crp_range
            }
        
        return per_day_ranges

    def _extract_lab_events(self, extracted_data: Dict) -> List[Dict]:
        """Extract lab result events"""
        events = []
        for lab in extracted_data.get("labs", []):
            if not isinstance(lab, dict):
                continue
            
            date = self._get_date(lab, ["date", "Date", "collected", "collection_date", "test_date", "result_date"])
            if date:
                test_name = lab.get("test_name", "Lab")
                value = lab.get("value", "")
                unit = lab.get("unit", "")
                abnormal = lab.get("abnormal", False)
                critical = lab.get("critical", False)
                
                # Build description with flags
                desc_parts = [test_name]
                if value:
                    desc_parts.append(value)
                if unit:
                    desc_parts.append(unit)
                
                description = ": ".join(desc_parts).strip() if len(desc_parts) > 1 else desc_parts[0]
                
                if critical:
                    description += " [CRITICAL]"
                elif abnormal:
                    description += " (ABNORMAL)"
                
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": date,
                    "event_type": "lab_result",
                    "description": description,
                    "source": "labs",
                    "details": lab,
                    "source_file": lab.get("source_file"),
                    "source_page": lab.get("source_page")
                })
        return events

    def _extract_imaging_events(self, extracted_data: Dict) -> List[Dict]:
        """Extract imaging study events"""
        events = []
        for img in extracted_data.get("imaging", []):
            if not isinstance(img, dict):
                continue
            
            date = self._get_date(img, ["date", "Date", "performed", "study_date", "performed_date", "exam_date"])
            if date:
                study_type = img.get("study_type", "Imaging Study")
                body_part = img.get("body_part", "")
                modality = img.get("modality", "")
                
                # Build description
                desc_parts = [study_type]
                if modality and modality.lower() not in study_type.lower():
                    desc_parts.append(f"({modality})")
                if body_part:
                    desc_parts.append(f"- {body_part}")
                
                description = " ".join(desc_parts).strip()
                
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": date,
                    "event_type": "imaging",
                    "description": description,
                    "source": "imaging",
                    "details": img,
                    "source_file": img.get("source_file"),
                    "source_page": img.get("source_page")
                })
        return events

    def _extract_diagnosis_events(self, extracted_data: Dict) -> List[Dict]:
        """Extract diagnosis events"""
        events = []
        for dx in extracted_data.get("diagnoses", []):
            # Handle both string and dict formats
            if isinstance(dx, str):
                continue  # Skip string-only diagnoses without dates
            
            if not isinstance(dx, dict):
                continue
            
            date = self._get_date(dx, ["date", "Date", "diagnosed_on", "onset_date", "diagnosis_date", "documented_date"])
            if date:
                dx_name = dx.get("name", "Unknown Diagnosis")
                dx_type = dx.get("type", "")
                dx_status = dx.get("status", "")
                
                # Build description
                desc_parts = [f"Diagnosed: {dx_name}"]
                if dx_type:
                    desc_parts.append(f"({dx_type})")
                if dx_status:
                    desc_parts.append(f"- {dx_status}")
                
                events.append({
                    "id": str(uuid.uuid4()),
                    "date": date,
                    "event_type": "diagnosis",
                    "description": " ".join(desc_parts).strip(),
                    "source": "diagnoses",
                    "details": dx,
                    "source_file": dx.get("source_file"),
                    "source_page": dx.get("source_page")
                })
        return events

    def _extract_social_factor_events(self, extracted_data: Dict) -> List[Dict]:
        """
        Extract social factor events (housing, caregiver, cognition, placement barriers).
        These MUST appear as labeled Social Factors timeline events.
        MUST NOT interpret or score - only factual descriptions.
        """
        events = []
        social_factors = extracted_data.get("social_factors", [])
        
        if not social_factors:
            return events
        
        for factor in social_factors:
            if not isinstance(factor, dict):
                continue
            
            # Get date - prefer explicit date, otherwise use null
            date = self._get_date(factor, ["date", "Date", "assessment_date", "documented_date"])
            
            # Get factor type and description
            factor_type = factor.get("factor_type", "").lower()
            description = factor.get("description", "")
            
            # If no description, skip (required for audit trail)
            if not description:
                continue
            
            # Build event description - label as "Social Factor" with type context
            if factor_type:
                # Map factor_type to readable label
                type_labels = {
                    "housing": "Housing",
                    "caregiver": "Caregiver",
                    "cognition": "Cognition",
                    "placement_barrier": "Placement Barrier"
                }
                type_label = type_labels.get(factor_type, "Social Factor")
                event_description = f"Social Factor ({type_label}): {description}"
            else:
                event_description = f"Social Factor: {description}"
            
            # Use date from factor if available, otherwise use admission date as fallback
            # (since social factors are often documented on admission)
            event_date = date
            if not event_date:
                # Try to get admission date from extracted_data if available
                # But only if we can't get a date from the factor itself
                # For now, skip events without dates to maintain strict chronology
                continue
            
            events.append({
                "id": str(uuid.uuid4()),
                "date": event_date,
                "event_type": "social_factor",
                "description": event_description,
                "source": "social_factors",
                "details": factor,
                "source_file": factor.get("source_file"),
                "source_page": factor.get("source_page")
            })
        
        return events

    def _extract_therapy_events(self, extracted_data: Dict) -> List[Dict]:
        """
        Extract therapy events (PT/OT/Speech) with functional status.
        These notes are often decisive for utilization review and discharge planning.
        """
        events = []
        therapy_notes = extracted_data.get("therapy_notes", [])
        functional_status = extracted_data.get("functional_status", [])
        
        # Extract events from therapy notes
        for therapy in therapy_notes:
            if not isinstance(therapy, dict):
                continue
            
            date = self._get_date(therapy, ["date", "Date", "assessment_date", "session_date"])
            if not date:
                continue
            
            therapy_type = therapy.get("therapy_type", "").upper()
            provider = therapy.get("provider", "")
            notes = therapy.get("notes", "")
            findings = therapy.get("findings", "")
            
            # Build description with therapy type and key information
            desc_parts = [f"{therapy_type} Assessment"]
            if provider:
                desc_parts.append(f"(Provider: {provider})")
            if findings:
                desc_parts.append(f"- {findings}")
            elif notes:
                # Use first sentence or truncate if too long
                note_preview = notes.split('.')[0][:100] if notes else ""
                if note_preview:
                    desc_parts.append(f"- {note_preview}")
            
            # Add functional status to description if available
            func_status = therapy.get("functional_status", {})
            if func_status:
                func_parts = []
                if func_status.get("mobility"):
                    func_parts.append(f"Mobility: {func_status['mobility']}")
                if func_status.get("ambulation"):
                    func_parts.append(f"Ambulation: {func_status['ambulation']}")
                if func_status.get("adl_status"):
                    func_parts.append(f"ADL: {func_status['adl_status']}")
                if func_status.get("cognitive_status"):
                    func_parts.append(f"Cognitive/Communication: {func_status['cognitive_status']}")
                if func_parts:
                    desc_parts.append(f"Functional Status: {', '.join(func_parts)}")
            
            description = " ".join(desc_parts)
            
            event = {
                "id": str(uuid.uuid4()),
                "date": date,
                "event_type": "therapy_assessment",
                "description": description,
                "source": "therapy_notes",
                "details": therapy,
                "source_file": therapy.get("source_file"),
                "source_page": therapy.get("source_page")
            }
            
            # Check if this includes ambulation/mobility (evidence signal)
            if func_status:
                mobility_status = func_status.get("mobility", "")
                ambulation_status = func_status.get("ambulation", "")
                if mobility_status or ambulation_status:
                    event["is_evidence_signal"] = True
                    event["evidence_signal_type"] = "ambulation"
            
            events.append(event)
        
        # Extract events from functional status assessments (if separate from therapy notes)
        for status in functional_status:
            if not isinstance(status, dict):
                continue
            
            date = self._get_date(status, ["date", "Date", "assessment_date"])
            if not date:
                continue
            
            assessment_type = status.get("assessment_type", "Functional Status")
            mobility = status.get("mobility", "")
            ambulation = status.get("ambulation", "")
            adl = status.get("adl_assistance_level", "")
            cognitive = status.get("cognitive_communication", "")
            
            # Build description with functional status details
            desc_parts = [f"{assessment_type} Assessment"]
            func_parts = []
            if mobility:
                func_parts.append(f"Mobility: {mobility}")
            if ambulation:
                func_parts.append(f"Ambulation: {ambulation}")
            if adl:
                func_parts.append(f"ADL: {adl}")
            if cognitive:
                func_parts.append(f"Cognitive/Communication: {cognitive}")
            
            if func_parts:
                desc_parts.append(f"Functional Status: {', '.join(func_parts)}")
            
            progress = status.get("progress_notes", "")
            if progress:
                progress_preview = progress.split('.')[0][:100] if progress else ""
                if progress_preview:
                    desc_parts.append(f"Progress: {progress_preview}")
            
            description = " ".join(desc_parts) if desc_parts else f"{assessment_type} Assessment"
            
            event = {
                "id": str(uuid.uuid4()),
                "date": date,
                "event_type": "therapy_assessment",
                "description": description,
                "source": "functional_status",
                "details": status,
                "source_file": status.get("source_file"),
                "source_page": status.get("source_page")
            }
            
            # Check if this includes ambulation/mobility (evidence signal)
            if ambulation:
                event["is_evidence_signal"] = True
                event["evidence_signal_type"] = "ambulation"
            
            events.append(event)
        
        return events

    async def _supplement_with_rag(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        existing_events: List[Dict]
    ) -> List[Dict]:
        """
        Supplement timeline with RAG-retrieved date-rich chunks
        
        Looks for additional temporal events not captured in structured extraction
        """
        # Import here to avoid circular imports
        from app.services.rag_retriever import rag_retriever
        from app.services.embedding_service import embedding_service
        from app.services.llm.llm_factory import get_tier1_llm_service, get_tier1_llm_service_for_user
        from app.core.config import settings
        
        additional_events = []
        
        # Query for date-rich chunks - no section filtering
        query = "admission date discharge date event date time progression clinical course"
        chunks = rag_retriever.retrieve_for_query(
            db=db,
            query=query,
            case_id=case_id,
            user_id=user_id,
            top_k=20  # Increased from 10
        )

        if not chunks:
            return []
        
        # Build context for LLM to extract additional events
        context_parts = []
        for chunk in chunks:
            context_parts.append(f"[Page {chunk.page_number}]\n{chunk.chunk_text}")
        
        context = "\n\n".join(context_parts)
        
        # Use Tier 1 LLM to extract additional temporal events (PHI allowed)
        if db and user_id:
            llm_service = get_tier1_llm_service_for_user(db, user_id)
        else:
            llm_service = get_tier1_llm_service()
        
        if not llm_service.is_available():
            return []
        
        # Use prompt service to render the timeline extraction prompt
        prompt_id = "timeline_extraction"
        variables = {"text": context}
        prompt = prompt_service.render_prompt(prompt_id, variables)
        system_message = prompt_service.get_system_message(prompt_id)
        
        if not system_message:
            logger.error(f"System message not found for prompt_id: {prompt_id}")
            raise ValueError(f"System message not found for prompt_id: {prompt_id}. Please ensure the prompt exists in the database.")
        
        try:
            # Determine provider for JSON format handling
            from app.services.llm.claude_service import ClaudeService
            from app.services.llm.openai_service import OpenAIService
            from app.services.llm_utils import EXTRACTION_RULES
            is_claude = isinstance(llm_service, ClaudeService)
            is_openai = isinstance(llm_service, OpenAIService)
            
            # Append centralized extraction instructions
            prompt_with_rules = prompt + EXTRACTION_RULES
            
            response, usage = await llm_service.chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": prompt_with_rules
                    }
                ],
                system_message=system_message,
                temperature=0.1,
                max_tokens=2000,  # Increased to handle longer timeline responses
                response_format={"type": "json_object"} if is_openai else None
            )
            
            # Track usage if user_id is available
            if user_id and db:
                try:
                    from app.services.usage_tracking_service import usage_tracking_service
                    if is_claude:
                        provider_name = "claude"
                        model_name = getattr(llm_service, 'model', settings.CLAUDE_MODEL)
                    elif is_openai:
                        provider_name = "openai"
                        model_name = getattr(llm_service, 'model', settings.OPENAI_MODEL)
                    else:
                        provider_name = settings.LLM_PROVIDER.lower()
                        model_name = settings.LLM_MODEL
                    
                    usage_tracking_service.track_llm_usage(
                        db=db,
                        user_id=user_id,
                        provider=provider_name,
                        model=model_name,
                        operation_type="timeline",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        case_id=case_id,
                        extra_metadata={
                            "operation": "timeline_rag_supplement",
                            "prompt_id": prompt_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track usage: {e}", exc_info=True)
            
            from app.services.llm_utils import extract_json_from_response
            try:
                result = extract_json_from_response(response)
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to parse JSON response from LLM: {e}. Response: {response[:200] if response else 'Empty'}")
                return additional_events  # Return empty list if parsing fails
            
            for event in result.get("events", []):
                if event.get("date"):
                    additional_events.append({
                        "id": str(uuid.uuid4()),
                        "date": event["date"],
                        "event_type": event.get("event_type", "event"),
                        "description": event.get("description", ""),
                        "source": "rag_supplement",
                        "details": {"rag_extracted": True}
                    })
                    
        except Exception as e:
            logger.warning(f"Failed to extract additional timeline events: {e}")
        
        return additional_events

    def _extract_summary_events(self, all_events: List[Dict]) -> List[Dict]:
        """
        Extract only major/important events for summary timeline
        
        Major events include:
        - Admissions and discharges
        - Major procedures (surgical procedures, invasive procedures)
        - Diagnoses (especially new diagnoses)
        - Critical/abnormal lab results
        - Major medication changes (start/stop of significant medications)
        - Imaging studies with significant findings
        - Emergency department visits
        - Transfers between units/facilities
        
        Excludes:
        - Routine vital signs
        - Normal lab results
        - Routine medication dose adjustments
        - Minor outpatient procedures
        """
        summary_events = []
        
        for event in all_events:
            event_type = event.get("event_type", "")
            details = event.get("details", {})
            
            # Always include major event types
            if event_type in [
                "diagnosis",
                "procedure",  # Include all procedures as major events
                "admission",
                "discharge",
                "transfer",
                "emergency_visit",
                "social_factor",  # Include social factors as major events (critical for discharge/admin days)
                "therapy_assessment"  # Include therapy assessments as major events (often decisive for utilization review)
            ]:
                summary_events.append(event)
            
            # Include critical/abnormal lab results
            elif event_type == "lab_result":
                is_critical = details.get("critical", False)
                is_abnormal = details.get("abnormal", False)
                if is_critical or is_abnormal:
                    summary_events.append(event)
            
            # Include major imaging studies (all imaging is typically significant)
            elif event_type == "imaging":
                summary_events.append(event)
            
            # Include medication starts/stops (major changes)
            elif event_type in ["medication_started", "medication_ended", "medication_changed"]:
                summary_events.append(event)
            
            # Exclude routine vital signs (vital_recorded events)
            # Exclude normal lab results (already handled above)
        
        return summary_events

    def _validate_event_consistency(self, events: List[Dict]) -> List[Dict]:
        """
        Validate and fix event consistency issues:
        - Ensure all required fields are present
        - Normalize date formats
        - Ensure event_type is valid
        - Remove invalid events
        """
        validated_events = []
        required_fields = ["id", "date", "event_type", "description"]
        valid_event_types = [
            "admission", "discharge", "transfer", "emergency_visit",
            "medication_started", "medication_ended", "medication_changed",
            "procedure", "lab_result", "vital_recorded", "imaging",
            "diagnosis", "social_factor", "therapy_assessment"
        ]
        
        for event in events:
            if not isinstance(event, dict):
                logger.warning(f"Skipping non-dict event: {type(event)}")
                continue
            
            # Check required fields
            missing_fields = [field for field in required_fields if not event.get(field)]
            if missing_fields:
                logger.warning(f"Event missing required fields {missing_fields}, skipping: {event.get('event_type', 'unknown')}")
                continue
            
            # Normalize date format
            if event.get("date"):
                normalized_date = self._normalize_date_format(str(event["date"]))
                if normalized_date:
                    event["date"] = normalized_date
                else:
                    logger.debug(f"Event has invalid date format '{event['date']}', skipping: {event.get('event_type', 'unknown')}")
                    continue
            else:
                logger.debug(f"Event missing date field, skipping: {event.get('event_type', 'unknown')}")
                continue
            
            # Validate event_type
            event_type = event.get("event_type", "").strip()
            if event_type not in valid_event_types:
                logger.warning(f"Event has invalid event_type '{event_type}', skipping")
                continue
            event["event_type"] = event_type
            
            # Ensure description is not empty
            description = (event.get("description") or "").strip()
            if not description:
                logger.warning(f"Event has empty description, using event_type: {event_type}")
                event["description"] = event_type.replace("_", " ").title()
            else:
                event["description"] = description
            
            # Ensure id is a string
            if not isinstance(event.get("id"), str):
                event["id"] = str(uuid.uuid4())
            
            validated_events.append(event)
        
        if len(validated_events) != len(events):
            logger.info(f"Event validation: {len(events)} events -> {len(validated_events)} valid events")
        
        return validated_events

    def _filter_events_without_sources(self, events: List[Dict]) -> List[Dict]:
        """
        Filter out events that don't have both source_file and source_page.
        This is CRITICAL for audit defense - every timeline event MUST have source references.
        
        Args:
            events: List of timeline events
            
        Returns:
            List of events that have both source_file and source_page
        """
        filtered = []
        filtered_count = 0
        
        for event in events:
            # Check for source_file (can be at event level or in details)
            source_file = event.get("source_file")
            if not source_file and isinstance(event.get("details"), dict):
                source_file = event.get("details", {}).get("source_file")
            
            # Check for source_page (can be at event level, as source_page, page_number, or in details)
            source_page = event.get("source_page") or event.get("page_number")
            if not source_page and isinstance(event.get("details"), dict):
                source_page = event.get("details", {}).get("source_page") or event.get("details", {}).get("page_number")
            
            # Only include events with both source_file and source_page
            if source_file and source_page:
                filtered.append(event)
            else:
                filtered_count += 1
                logger.warning(
                    f"Timeline event filtered out due to missing source: "
                    f"type={event.get('event_type')}, date={event.get('date')}, "
                    f"has_file={bool(source_file)}, has_page={bool(source_page)}"
                )
        
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} timeline events without source references (audit requirement)")
        
        return filtered

    def _validate_event_descriptions(self, events: List[Dict]) -> List[Dict]:
        """
        Ensure event descriptions are factual only, no interpretation.
        Remove any language that suggests decisions, recommendations, or interpretation.
        This is critical for maintaining neutrality in timeline events.
        """
        interpretation_patterns = [
            r'\b(should|must|recommended|suggested|indicated|warranted|appropriate)\b',
            r'\b(medical necessity|necessity|requires|needed|necessary)\b',
            r'\b(beneficial|effective|improvement|worsening|decline|deterioration)\b',
            r'\b(poorly controlled|well controlled|inadequate|sufficient)\b',
            r'\b(failed|successful|unsuccessful)\b',
            r'\b(high-risk|low-risk|severe|mild|moderate)\b',  # Severity scoring
            r'\b(critical|urgent|emergent)\b',  # Only if used as severity assessment
        ]
        
        for event in events:
            description = event.get("description", "")
            if not description:
                continue
            
            cleaned_description = description
            
            # Remove interpretation language patterns
            for pattern in interpretation_patterns:
                cleaned_description = re.sub(pattern, '', cleaned_description, flags=re.IGNORECASE)
            
            # Clean up extra whitespace
            cleaned_description = re.sub(r'\s+', ' ', cleaned_description).strip()
            
            # Only update if cleaning changed something significant
            if cleaned_description and cleaned_description != description:
                # Keep original if cleaning removed too much (empty or too short)
                if len(cleaned_description) < 3:
                    logger.debug(f"Description cleaning resulted in too-short text, keeping original: {description[:50]}")
                else:
                    event["description"] = cleaned_description
        
        return events

    def _sort_timeline(self, events: List[Dict]) -> List[Dict]:
        """Sort timeline events by date - optimized with pre-parsed dates"""
        # Pre-parse all dates once to avoid repeated parsing in sort key function
        parsed_events = []
        for event in events:
            date_str = event.get("date", "")
            # Use utility function for consistent parsing
            parsed_date = parse_date_for_sort(date_str)
            parsed_events.append((parsed_date, event))
        
        # Sort by pre-parsed datetime (more efficient than parsing in key function)
        parsed_events.sort(key=lambda x: x[0])
        
        # Return just the events in sorted order
        return [event for _, event in parsed_events]

    def _deduplicate_events(self, events: List[Dict]) -> List[Dict]:
        """Remove duplicate or very similar events"""
        seen = set()
        unique_events = []
        
        for event in events:
            # Create a key based on date and description
            key = f"{event.get('date', '')}|{event.get('description', '')[:50].lower()}"
            
            if key not in seen:
                seen.add(key)
                unique_events.append(event)
        
        return unique_events

    def group_events_by_date(self, timeline: List[Dict]) -> Dict[str, List[Dict]]:
        """Group timeline events by date"""
        grouped = {}
        for event in timeline:
            date = event.get("date", "Unknown")
            if date not in grouped:
                grouped[date] = []
            grouped[date].append(event)
        return grouped

    def group_events_by_type(self, timeline: List[Dict]) -> Dict[str, List[Dict]]:
        """Group timeline events by event type"""
        grouped = {}
        for event in timeline:
            event_type = event.get("event_type", "other")
            if event_type not in grouped:
                grouped[event_type] = []
            grouped[event_type].append(event)
        return grouped


# Singleton instance
timeline_service = TimelineService()
