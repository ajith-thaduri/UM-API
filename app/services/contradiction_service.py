"""Potential missing information detection service"""

from datetime import datetime, timedelta
from typing import Dict, List
import uuid
import logging
from collections import defaultdict

from app.utils.date_utils import parse_date_for_sort

logger = logging.getLogger(__name__)


class ContradictionService:
    """Service for detecting potential missing information and items that may require review"""

    def detect_contradictions(
        self, extracted_data: Dict, timeline: List[Dict], file_page_mapping: Dict = None
    ) -> List[Dict]:
        """
        Detect potential missing information or items that may require review

        Args:
            extracted_data: Extracted clinical information
            timeline: Timeline of events
            file_page_mapping: Mapping of file_id -> {page_num -> text} for source tracking

        Returns:
            List of potential missing information items with source information
        """
        potential_issues = []

        # Detect duplicate entries
        potential_issues.extend(self._detect_duplicates(timeline, file_page_mapping))

        # Detect date mismatches
        potential_issues.extend(self._detect_date_mismatches(timeline, file_page_mapping))

        # Detect copy-forward errors (identical repeated values)
        potential_issues.extend(self._detect_copy_forward(extracted_data, file_page_mapping))

        # Detect conflicting data
        potential_issues.extend(self._detect_conflicts(extracted_data, file_page_mapping))

        # Detect radiology inconsistencies (summaries vs findings)
        potential_issues.extend(self._detect_radiology_inconsistency(extracted_data))

        # Detect missing expected data (Checklist detector)
        potential_issues.extend(self._detect_missing_expected_data(extracted_data))

        return potential_issues

    def _detect_duplicates(self, timeline: List[Dict], file_page_mapping: Dict = None) -> List[Dict]:
        """Detect potential duplicate timeline entries"""
        potential_issues = []
        seen_events = {}

        for event in timeline:
            # Create a signature for the event
            signature = f"{event.get('date')}_{event.get('event_type')}_{event.get('description')}"

            if signature in seen_events:
                # Get source information if available
                sources = []
                if file_page_mapping and event.get("details"):
                    source_file = event.get("details", {}).get("source_file")
                    source_page = event.get("details", {}).get("source_page")
                    if source_file and source_page:
                        sources.append({"file": source_file, "page": source_page})
                
                potential_issues.append({
                    "id": str(uuid.uuid4()),
                    "type": "duplicate_entry",
                    "description": f"Potential duplicate entry: {event.get('description')} on {event.get('date')}",
                    "affected_events": [seen_events[signature], event.get("id")],
                    "suggestion": "May require review to confirm if this is a duplicate entry",
                    "sources": sources if sources else [],
                    "term": event.get('description')
                })
            else:
                seen_events[signature] = event.get("id")

        return potential_issues

    def _detect_date_mismatches(self, timeline: List[Dict], file_page_mapping: Dict = None) -> List[Dict]:
        """
        Detect impossible date sequences or chronological inconsistencies.
        
        Algorithm:
        1. Filter admission/discharge events using event_type (primary) and description (fallback)
        2. Parse dates using parse_date_for_sort() for robust format handling
        3. Sort chronologically
        4. Detect errors: discharge before admission (with same-day tolerance)
        5. Handle multiple admission/discharge pairs independently
        
        Args:
            timeline: List of timeline events
            file_page_mapping: Optional mapping for source tracking
            
        Returns:
            List of chronological error contradictions
        """
        contradictions = []
        
        # Parse and sort all events by date using robust date parsing
        sorted_events = []
        for event in timeline:
            date_str = event.get("date")
            if not date_str:
                continue
            
            # Use the same robust date parsing as timeline service
            parsed_date = parse_date_for_sort(date_str)
            # Only include events with valid dates (not epoch fallback)
            if parsed_date > datetime(1970, 1, 1):
                sorted_events.append((parsed_date, event))
            else:
                logger.debug(f"Skipping event with invalid date: {event.get('id', 'unknown')} - {date_str}")
        
        sorted_events.sort(key=lambda x: x[0])
        
        # Filter admission/discharge events using event_type (primary) and description (fallback)
        admission_discharge_events = []
        for dt, event in sorted_events:
            event_type = event.get("event_type", "").lower()
            description = event.get("description", "").lower()
            
            # Use event_type first (more reliable), fallback to description for backward compatibility
            is_admission = (
                event_type == "admission" or 
                ("admission" in description or "admitted" in description)
            )
            is_discharge = (
                event_type == "discharge" or 
                ("discharge" in description or "discharged" in description)
            )
            
            if is_admission:
                admission_discharge_events.append((dt, event, "admission"))
            elif is_discharge:
                admission_discharge_events.append((dt, event, "discharge"))
        
        # Detect chronological errors: discharge before admission
        # Algorithm: For each discharge, check if there's an admission after it without a matching discharge
        # Track admissions and their matching discharges
        admissions = []  # List of (date, event) tuples
        discharges = []  # List of (date, event) tuples
        
        for dt, event, event_type in admission_discharge_events:
            if event_type == "admission":
                admissions.append((dt, event))
            elif event_type == "discharge":
                discharges.append((dt, event))
        
        # Check each discharge against admissions
        for disc_dt, disc_event in discharges:
            # Find admissions that come after this discharge
            for adm_dt, adm_event in admissions:
                # Same-day tolerance: if dates are within 1 day, consider valid (not an error)
                time_diff = abs((disc_dt - adm_dt).total_seconds())
                same_day = time_diff < timedelta(days=1).total_seconds()
                
                # Check if discharge is before admission (chronological error)
                if not same_day and disc_dt < adm_dt:
                    # Check if there's already a discharge for this admission (valid pair)
                    # If there's a discharge between this discharge and the admission, it's a different pair
                    has_matching_discharge = any(
                        other_disc_dt > adm_dt and other_disc_dt < disc_dt + timedelta(days=365)
                        for other_disc_dt, _ in discharges
                        if other_disc_dt != disc_dt
                    )
                    
                    # If no matching discharge found, this is an error
                    # Also check if this discharge is the first event (before any admission)
                    is_first_discharge = disc_dt < min((adm[0] for adm in admissions), default=disc_dt)
                    
                    if is_first_discharge or not has_matching_discharge:
                        contradictions.append({
                            "id": str(uuid.uuid4()),
                            "type": "chronological_error",
                            "description": f"Impossible sequence: Discharge documented on {disc_dt.strftime('%m/%d/%Y')} is before Admission on {adm_dt.strftime('%m/%d/%Y')}",
                            "affected_events": [adm_event.get("id"), disc_event.get("id")],
                            "suggestion": "Verify record dates for admission and discharge synchronization",
                            "sources": self._get_sources_from_events([adm_event, disc_event])
                        })
                        logger.info(f"Detected chronological error: Discharge {disc_dt.strftime('%m/%d/%Y')} before Admission {adm_dt.strftime('%m/%d/%Y')}")
                        break  # Report error once per discharge-admission pair

        return contradictions

    def _get_sources_from_events(self, events: List[Dict]) -> List[Dict]:
        """Helper to extract sources from a list of timeline events"""
        sources = []
        for event in events:
            if not event: continue
            # Check event root first
            s_file = event.get("source_file")
            s_page = event.get("source_page")
            
            # Then check details
            if not s_file:
                s_file = event.get("details", {}).get("source_file")
            if not s_page:
                s_page = event.get("details", {}).get("source_page")
                
            if s_file and s_page:
                sources.append({
                    "file": s_file, 
                    "page": s_page,
                    "term": event.get("description"),
                    "bbox": event.get("bbox") or event.get("details", {}).get("bbox") # Keep as secondary fallback
                })
        return sources

    def _detect_copy_forward(self, extracted_data: Dict, file_page_mapping: Dict = None) -> List[Dict]:
        """Detect potential copy-forward patterns (identical repeated values)"""
        potential_issues = []

        # Check vitals for identical repeated values
        vitals_by_type = defaultdict(list)
        for vital in extracted_data.get("vitals", []):
            vitals_by_type[vital.get("type")].append(vital)

        for vital_type, vitals in vitals_by_type.items():
            if len(vitals) >= 3:
                # Check if 3+ consecutive measurements are identical
                values = [v.get("value") for v in vitals]
                if len(set(values)) == 1:  # All values are the same
                    # Get source information
                    sources = []
                    for vital in vitals:
                        source_file = vital.get("source_file")
                        source_page = vital.get("source_page")
                        if source_file and source_page:
                            sources.append({
                                "file": source_file, 
                                "page": source_page,
                                "term": str(vital.get("value")) if vital.get("value") else (vital.get("type") or vital.get("name")),
                                "bbox": vital.get("bbox") # Fallback
                            })
                    
                    # Sort sources by page number for logical progression
                    sources.sort(key=lambda x: (x.get("file", ""), x.get("page", 0)))
                    
                    potential_issues.append({
                        "id": str(uuid.uuid4()),
                        "type": "copy_forward",
                        "description": f"Potential copy-forward pattern: {vital_type} shows {len(values)} identical values ({values[0]})",
                        "affected_events": [],
                        "suggestion": "May require review to verify if measurements are truly identical",
                        "sources": sources
                    })

        # Check labs for identical repeated results
        labs_by_test = defaultdict(list)
        for lab in extracted_data.get("labs", []):
            labs_by_test[lab.get("test_name")].append(lab)

        for test_name, labs in labs_by_test.items():
            if len(labs) >= 3:
                values = [l.get("value") for l in labs]
                if len(set(values)) == 1:
                    # Get source information
                    sources = []
                    for lab in labs:
                        source_file = lab.get("source_file")
                        source_page = lab.get("source_page")
                        if source_file and source_page:
                            sources.append({
                                "file": source_file, 
                                "page": source_page,
                                "term": str(lab.get("value")) if lab.get("value") else lab.get("test_name"),
                                "bbox": lab.get("bbox") # Fallback
                            })
                    
                    # Sort sources by page number
                    sources.sort(key=lambda x: (x.get("file", ""), x.get("page", 0)))
                    
                    potential_issues.append({
                        "id": str(uuid.uuid4()),
                        "type": "copy_forward",
                        "description": f"Potential copy-forward pattern: {test_name} shows {len(values)} identical results ({values[0]})",
                        "affected_events": [],
                        "suggestion": "May require review to verify if results are truly identical",
                        "sources": sources
                    })

        return potential_issues

    def _detect_conflicts(self, extracted_data: Dict, file_page_mapping: Dict = None) -> List[Dict]:
        """Detect primary clinical conflicts and semantic inconsistencies"""
        potential_issues = []
        
        # 1. Medication vs Allergies
        allergies_raw = extracted_data.get("allergies", [])
        allergies = []
        for a in allergies_raw:
            if isinstance(a, str):
                allergies.append(a.lower())
            elif isinstance(a, dict):
                allergen = a.get("allergen", "")
                if allergen:
                    allergies.append(allergen.lower())
        
        for med in extracted_data.get("medications", []):
            med_name_lower = med.get("name", "").lower()
            for allergy in allergies:
                if allergy and (allergy in med_name_lower or med_name_lower in allergy):
                    sources = []
                    m_file, m_page = med.get("source_file"), med.get("source_page")
                    if m_file and m_page:
                        sources.append({"file": m_file, "page": m_page})
                    
                    potential_issues.append({
                        "id": str(uuid.uuid4()),
                        "type": "clinical_conflict",
                        "description": f"Potential Safety Alert: Medication '{med.get('name')}' documented while patient has allergy to '{allergy}'",
                        "affected_events": [],
                        "suggestion": "Cross-check administration records with allergy verification steps",
                        "sources": [
                            {
                                "file": m_file, 
                                "page": m_page,
                                "term": med.get("name"),
                                "bbox": med.get("bbox") # Fallback
                            }
                        ]
                    })

        # 2. Diagnoses vs Treatment Gaps
        diagnoses = [d.get("name", "").lower() if isinstance(d, dict) else str(d).lower() 
                    for d in extracted_data.get("diagnoses", [])]
        medications = [m.get("name", "").lower() for m in extracted_data.get("medications", [])]
        
        critical_treatments = {
            "pneumonia": ["cftr", "azithr", "levoflo", "vanco", "ceftr", "antibiotic"],
            "infection": ["antibiotic", "penicillin", "cepha"],
            "hypertension": ["lisino", "amlodi", "metopro", "losartan", "bp med"],
            "diabetes": ["insulin", "metformin", "glipizide"]
        }
        
        for condition, drug_patterns in critical_treatments.items():
            if any(condition in dx for dx in diagnoses):
                has_treatment = any(any(pattern in med for pattern in drug_patterns) for med in medications)
                if not has_treatment:
                    potential_issues.append({
                        "id": str(uuid.uuid4()),
                        "type": "treatment_gap",
                        "description": f"Potential Gap: Diagnosis of '{condition}' present but no corresponding treatment found in medication list",
                        "affected_events": [],
                        "suggestion": "Verify if medications were omitted from extraction or if treatment plan is documented elsewhere",
                        "sources": []
                    })
        
        # 3. Conflicting Lab Results (e.g. Blood Type)
        labs_by_name = defaultdict(list)
        for lab in extracted_data.get("labs", []):
            name = lab.get("test_name", "").lower()
            if name:
                labs_by_name[name].append(lab)
        
        # Static labs that should never change
        static_labs = ["blood type", "rh factor", "gender", "race"]
        for test_name, labs in labs_by_name.items():
            if any(static in test_name for static in static_labs):
                values = [l.get("value", "").strip().upper() for l in labs]
                unique_values = set(v for v in values if v)
                if len(unique_values) > 1:
                    potential_issues.append({
                        "id": str(uuid.uuid4()),
                        "type": "clinical_conflict",
                        "description": f"Conflicting Lab Results: Multiple values found for static lab '{test_name}': {', '.join(unique_values)}",
                        "affected_events": [],
                        "suggestion": "Verify correct lab results as this value should be constant.",
                        "sources": self._get_sources_from_labs(labs)
                    })
        
        return potential_issues

    def _get_sources_from_labs(self, labs: List[Dict]) -> List[Dict]:
        """Helper to extract sources from a list of lab results"""
        sources = []
        for lab in labs:
            s_file = lab.get("source_file")
            s_page = lab.get("source_page")
            if s_file and s_page:
                sources.append({
                    "file": s_file,
                    "page": s_page,
                    "term": lab.get("test_name"),
                    "bbox": lab.get("bbox")
                })
        return sources

    def _detect_radiology_inconsistency(self, extracted_data: Dict) -> List[Dict]:
        """Detect internal inconsistencies in radiology reports (Summary vs Findings)"""
        potential_issues = []
        imaging_results = extracted_data.get("imaging", [])

        for img in imaging_results:
            findings = str(img.get("findings", "")).lower()
            impression = str(img.get("impression", "")).lower()
            study_type = img.get("study_type", "Imaging")
            
            if not findings or not impression:
                continue
                
            # Key clinical markers to check for contradictions
            indicators = [
                ("fracture", ["no fracture", "without fracture", "negative for fracture"]),
                ("hemorrhage", ["no hemorrhage", "no bleeding", "negative for hemorrhage"]),
                ("pneumonia", ["no pneumonia", "lungs are clear", "no acute process"]),
                ("mass", ["no mass", "no suspicious mass"]),
                ("nodule", ["no nodule"]),
                ("clot", ["no clot", "no thrombus", "non-occlusive"]),
                ("acute", ["no acute", "chronic only", "resolved"])
            ]
            
            for positive, negatives in indicators:
                # If Findings mention the positive finding (e.g. "fracture present")
                # but Impression uses one of the negative phrases
                has_positive_finding = positive in findings and not any(neg in findings for neg in negatives)
                has_negative_summary = any(neg in impression for neg in negatives)
                
                # Reverse check: Negative findings but positive impression (less common but possible)
                has_negative_finding = any(neg in findings for neg in negatives)
                has_positive_summary = positive in impression and not any(neg in impression for neg in negatives)

                if (has_positive_finding and has_negative_summary) or (has_negative_finding and has_positive_summary):
                    sources = []
                    s_file = img.get("source_file")
                    s_page = img.get("source_page")
                    if s_file and s_page:
                        sources.append({
                            "file": s_file,
                            "page": s_page,
                            "term": positive,
                            "bbox": img.get("bbox")
                        })
                    
                    potential_issues.append({
                        "id": str(uuid.uuid4()),
                        "type": "radiology_inconsistency",
                        "description": f"Potential Radiology Inconsistency: {study_type} findings mention '{positive}' but the summary/impression suggests otherwise.",
                        "affected_events": [],
                        "suggestion": f"Potential internal inconsistency detected. Please review the detailed findings vs the radiologist's impression for this {study_type} report.",
                        "sources": sources
                    })
                    break # One issue per study is enough
                    
        return potential_issues

    def _detect_missing_expected_data(self, extracted_data: Dict) -> List[Dict]:
        """
        Checklist detector for core clinical indicators.
        Flags missing items like Vitals, GCS/Cognition for neuro cases, etc.
        """
        potential_issues = []
        
        # 1. Check for Vitals
        vitals = extracted_data.get("vitals", [])
        if not vitals:
            potential_issues.append({
                "id": str(uuid.uuid4()),
                "type": "missing_information",
                "description": "Core Clinical Data Missing: No Vital Signs (BP, HR, Temp, etc.) were explicitly documented in the provided records.",
                "affected_events": [],
                "suggestion": "Review records to confirm if vitals were captured or if they are truly missing from the documentation.",
                "sources": []
            })
            
        # 2. Check for Neuro-specific indicators (GCS/Cognition)
        diagnoses = [d.get("name", "").lower() if isinstance(d, dict) else str(d).lower() 
                    for d in extracted_data.get("diagnoses", [])]
        
        neuro_keywords = ["stroke", "brain", "neuro", "seizure", "tbi", "concussion", "dementia", "hemorrhage", "infarct"]
        is_neuro_case = any(any(kw in dx for kw in neuro_keywords) for dx in diagnoses)
        
        # Get history text for use in multiple checks below
        history = extracted_data.get("history", {})
        if isinstance(history, str):
            history_text = history.lower()
        else:
            history_text = str(history).lower()
        
        if is_neuro_case:
            # Check for GCS or specific cognitive assessment
                
            social_factors = extracted_data.get("social_factors", [])
            has_cognition = any("cognition" in str(sf).lower() or "cognitive" in str(sf).lower() for sf in social_factors)
            has_gcs = "gcs" in history_text or "glasgow" in history_text
            
            if not has_gcs and not has_cognition:
                potential_issues.append({
                    "id": str(uuid.uuid4()),
                    "type": "missing_information",
                    "description": "Neuro Case Quality Alert: Diagnosis suggest a neurological condition, but no GCS score or Cognitive Assessment was explicitly documented.",
                    "affected_events": [],
                    "suggestion": "Verify if neurological assessments or GCS scores are present in nursing or physician notes.",
                    "sources": []
                })

        # 3. Check for Physical Exam (in history or functional status)
        functional_status = extracted_data.get("functional_status", [])
        if not functional_status and not history_text: # Very basic check
             potential_issues.append({
                "id": str(uuid.uuid4()),
                "type": "missing_information",
                "description": "Quality Alert: No Physical Exam or Functional Status (mobility/ADLs) was explicitly documented.",
                "affected_events": [],
                "suggestion": "Confirm if therapy notes or nursing assessments contain functional status information.",
                "sources": []
            })

        return potential_issues


# Singleton instance
contradiction_service = ContradictionService()

