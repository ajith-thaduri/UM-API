"""Evidence Signals Extraction Service

Extracts key clinical evidence signals without classification or decision-making.
Surfaces raw evidence for MD review:
- IV→PO transitions (medication route changes)
- Room air (oxygen support discontinuation)
- Ambulation (mobility progression)
"""

import re
import uuid
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EvidenceSignalsService:
    """Service for extracting evidence signals from clinical data"""

    def extract_signals(
        self,
        extracted_data: Dict,
        timeline: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Extract evidence signals from clinical data and timeline.
        
        Returns list of evidence signals with:
        - signal_type: "iv_to_po", "room_air", "ambulation"
        - date: Date of signal (MM/DD/YYYY format)
        - description: Factual description of the signal
        - source: Source of information (medications, vitals, procedures, etc.)
        - details: Additional context
        - source_file: Source file if available
        - source_page: Source page if available
        """
        signals = []
        
        # Extract IV→PO transitions from medications
        iv_to_po_signals = self._extract_iv_to_po_transitions(extracted_data)
        signals.extend(iv_to_po_signals)
        
        # Extract room air transitions from vitals/timeline
        room_air_signals = self._extract_room_air_transitions(extracted_data, timeline)
        signals.extend(room_air_signals)
        
        # Extract ambulation signals from procedures/timeline
        ambulation_signals = self._extract_ambulation_signals(extracted_data, timeline)
        signals.extend(ambulation_signals)
        
        # Sort by date
        signals.sort(key=lambda x: self._parse_date_for_sort(x.get("date", "")))
        
        return signals

    def _extract_iv_to_po_transitions(self, extracted_data: Dict) -> List[Dict]:
        """Extract IV to PO medication route transitions"""
        signals = []
        medications = extracted_data.get("medications", [])
        
        if not medications:
            return signals
        
        # Group medications by name to detect route changes
        med_by_name = {}
        for med in medications:
            name = med.get("name", "").strip()
            if name:
                name_key = name.lower().strip()
                if name_key not in med_by_name:
                    med_by_name[name_key] = []
                med_by_name[name_key].append(med)
        
        # Process each medication group to find IV→PO transitions
        for med_name_key, med_list in med_by_name.items():
            # Sort by start_date to track chronological changes
            sorted_meds = sorted(
                med_list,
                key=lambda m: self._parse_date_for_sort(
                    self._get_date(m, ["start_date", "startDate", "date", "started"])
                )
            )
            
            prev_med = None
            for med in sorted_meds:
                if prev_med:
                    prev_route = (prev_med.get("route") or "").strip().lower()
                    curr_route = (med.get("route") or "").strip().lower()
                    
                    # Check for IV→PO transition
                    is_iv_prev = any(iv_term in prev_route for iv_term in ["iv", "intravenous", "i.v.", "i v"])
                    is_po_curr = any(po_term in curr_route for po_term in ["po", "oral", "by mouth", "p.o.", "p o"])
                    
                    if is_iv_prev and is_po_curr:
                        change_date = (
                            self._get_date(med, ["start_date", "startDate", "date", "started"]) or
                            self._get_date(prev_med, ["end_date", "endDate", "date"])
                        )
                        
                        if change_date:
                            med_name = med.get("name", "Medication")
                            signals.append({
                                "id": str(uuid.uuid4()),
                                "signal_type": "iv_to_po",
                                "date": change_date,
                                "description": f"{med_name}: Route changed from IV to PO",
                                "source": "medications",
                                "details": {
                                    "medication": med_name,
                                    "previous_route": prev_med.get("route"),
                                    "current_route": med.get("route"),
                                    "previous_dosage": prev_med.get("dosage"),
                                    "current_dosage": med.get("dosage"),
                                },
                                "source_file": med.get("source_file") or prev_med.get("source_file"),
                                "source_page": med.get("source_page") or prev_med.get("source_page"),
                            })
                
                prev_med = med
        
        return signals

    def _extract_room_air_transitions(
        self,
        extracted_data: Dict,
        timeline: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """Extract room air transitions (oxygen support discontinuation)"""
        signals = []
        
        # Check vitals for oxygen-related information
        vitals = extracted_data.get("vitals", [])
        
        # Look for oxygen-related notes in vitals
        oxygen_vitals = []
        for vital in vitals:
            vital_type = (vital.get("type") or "").lower()
            vital_notes = (vital.get("notes") or "").lower()
            vital_description = (str(vital.get("value", "")) + " " + str(vital.get("unit", ""))).lower()
            
            # Check if this is oxygen-related
            oxygen_keywords = ["oxygen", "o2", "fiO2", "room air", "ra", "nc", "nasal cannula", 
                              "ventilator", "vent", "biPap", "cpap", "high flow"]
            
            if any(keyword in vital_type or keyword in vital_notes or keyword in vital_description 
                   for keyword in oxygen_keywords):
                oxygen_vitals.append(vital)
        
        # Look for "room air" mentions (discontinuation of oxygen support)
        # Sort by date to detect transitions
        oxygen_vitals.sort(key=lambda v: self._parse_date_for_sort(self._get_date(v, ["date"])))
        
        room_air_found = False
        prev_oxygen_support = None
        
        for vital in oxygen_vitals:
            vital_type = (vital.get("type") or "").lower()
            vital_notes = (vital.get("notes") or "").lower()
            vital_value = str(vital.get("value", "")).lower()
            vital_unit = str(vital.get("unit", "")).lower()
            combined_text = f"{vital_type} {vital_notes} {vital_value} {vital_unit}".lower()
            
            # Check for room air mentions
            room_air_keywords = ["room air", "ra", "no oxygen", "off oxygen", "discontinued oxygen",
                                "o2 discontinued", "oxygen discontinued", "no o2", "off o2"]
            
            if any(keyword in combined_text for keyword in room_air_keywords):
                # Also check if previous vital showed oxygen support
                if prev_oxygen_support and not room_air_found:
                    # Potential transition to room air
                    signal_date = self._get_date(vital, ["date"])
                    if signal_date:
                        signals.append({
                            "id": str(uuid.uuid4()),
                            "signal_type": "room_air",
                            "date": signal_date,
                            "description": "Patient on room air (oxygen support discontinued)",
                            "source": "vitals",
                            "details": {
                                "vital_type": vital.get("type"),
                                "value": vital.get("value"),
                                "unit": vital.get("unit"),
                                "notes": vital.get("notes"),
                                "previous_oxygen_support": prev_oxygen_support.get("type") or "Unknown",
                            },
                            "source_file": vital.get("source_file"),
                            "source_page": vital.get("source_page"),
                        })
                        room_air_found = True
                elif not room_air_found:
                    # First mention of room air
                    signal_date = self._get_date(vital, ["date"])
                    if signal_date:
                        signals.append({
                            "id": str(uuid.uuid4()),
                            "signal_type": "room_air",
                            "date": signal_date,
                            "description": "Patient on room air",
                            "source": "vitals",
                            "details": {
                                "vital_type": vital.get("type"),
                                "value": vital.get("value"),
                                "unit": vital.get("unit"),
                                "notes": vital.get("notes"),
                            },
                            "source_file": vital.get("source_file"),
                            "source_page": vital.get("source_page"),
                        })
            
            # Track previous oxygen support for transition detection
            oxygen_support_keywords = ["oxygen", "o2", "fiO2", "nc", "nasal cannula", 
                                      "ventilator", "vent", "biPap", "cpap", "high flow"]
            if any(keyword in combined_text for keyword in oxygen_support_keywords) and "room air" not in combined_text and "no oxygen" not in combined_text:
                prev_oxygen_support = vital
        
        # Also check timeline for oxygen-related events
        if timeline:
            for event in timeline:
                event_description = (event.get("description") or "").lower()
                event_type = (event.get("event_type") or "").lower()
                
                room_air_keywords = ["room air", "off oxygen", "discontinued oxygen", "no oxygen", "o2 discontinued"]
                
                if any(keyword in event_description for keyword in room_air_keywords):
                    signal_date = event.get("date")
                    if signal_date:
                        # Check if we already have this signal (avoid duplicates)
                        existing = any(
                            s.get("signal_type") == "room_air" and s.get("date") == signal_date
                            for s in signals
                        )
                        if not existing:
                            signals.append({
                                "id": str(uuid.uuid4()),
                                "signal_type": "room_air",
                                "date": signal_date,
                                "description": event.get("description", "Patient on room air"),
                                "source": event.get("source", "timeline"),
                                "details": event.get("details", {}),
                                "source_file": event.get("source_file"),
                                "source_page": event.get("source_page"),
                            })
        
        return signals

    def _extract_ambulation_signals(
        self,
        extracted_data: Dict,
        timeline: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """Extract ambulation/mobility signals"""
        signals = []
        
        # Check procedures for ambulation-related activities
        procedures = extracted_data.get("procedures", [])
        
        ambulation_keywords = [
            "ambulation", "ambulate", "walking", "walk", "mobility", "mobilization",
            "physical therapy", "pt", "out of bed", "oob", "up ad lib", "up with assistance",
            "assist to chair", "sitting", "standing", "transfer", "gait", "up to chair"
        ]
        
        for procedure in procedures:
            proc_name = (procedure.get("name") or "").lower()
            proc_notes = (procedure.get("notes") or "").lower()
            proc_findings = (procedure.get("findings") or "").lower()
            
            combined_text = f"{proc_name} {proc_notes} {proc_findings}".lower()
            
            if any(keyword in combined_text for keyword in ambulation_keywords):
                proc_date = self._get_date(procedure, ["date"])
                if proc_date:
                    signals.append({
                        "id": str(uuid.uuid4()),
                        "signal_type": "ambulation",
                        "date": proc_date,
                        "description": procedure.get("name") or "Ambulation/Mobility activity",
                        "source": "procedures",
                        "details": {
                            "procedure_name": procedure.get("name"),
                            "notes": procedure.get("notes"),
                            "findings": procedure.get("findings"),
                            "provider": procedure.get("provider"),
                        },
                        "source_file": procedure.get("source_file"),
                        "source_page": procedure.get("source_page"),
                    })
        
        # Check timeline for ambulation-related events
        if timeline:
            for event in timeline:
                event_description = (event.get("description") or "").lower()
                event_type = (event.get("event_type") or "").lower()
                
                if any(keyword in event_description for keyword in ambulation_keywords):
                    signal_date = event.get("date")
                    if signal_date:
                        # Check if we already have this signal (avoid duplicates)
                        existing = any(
                            s.get("signal_type") == "ambulation" and 
                            s.get("date") == signal_date and
                            s.get("description", "").lower() == event.get("description", "").lower()
                            for s in signals
                        )
                        if not existing:
                            signals.append({
                                "id": str(uuid.uuid4()),
                                "signal_type": "ambulation",
                                "date": signal_date,
                                "description": event.get("description", "Ambulation/Mobility activity"),
                                "source": event.get("source", "timeline"),
                                "details": event.get("details", {}),
                                "source_file": event.get("source_file"),
                                "source_page": event.get("source_page"),
                            })
        
        return signals

    def _get_date(self, item: Dict, date_keys: List[str]) -> Optional[str]:
        """Extract date from item using multiple possible keys"""
        for key in date_keys:
            date_value = item.get(key)
            if date_value:
                # Return as-is, dates should already be normalized from timeline service
                return str(date_value).strip()
        return None

    def _parse_date_for_sort(self, date_str: Optional[str]) -> datetime:
        """Parse date string for sorting purposes"""
        if not date_str:
            return datetime.min
        
        try:
            # Try MM/DD/YYYY format
            if "/" in date_str:
                parts = date_str.split("/")
                if len(parts) == 3:
                    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                    return datetime(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return datetime.min


# Singleton instance
evidence_signals_service = EvidenceSignalsService()

