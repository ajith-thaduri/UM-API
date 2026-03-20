"""Extraction schemas"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class ContradictionType(str, Enum):
    """Contradiction type enumeration"""

    DATE_MISMATCH = "date_mismatch"
    DUPLICATE_ENTRY = "duplicate_entry"
    COPY_FORWARD = "copy_forward"
    CONFLICTING_DATA = "conflicting_data"
    MISSING_DATA = "missing_data"


class TimelineEvent(BaseModel):
    """Timeline event schema"""

    id: str
    date: str
    event_type: str
    description: str
    source: str
    page_number: Optional[int] = None


class Contradiction(BaseModel):
    """Contradiction detection schema"""

    id: str
    type: ContradictionType
    description: str
    affected_events: List[str]
    severity: str = Field(..., pattern="^(high|medium|low)$")
    suggestion: Optional[str] = None


class Medication(BaseModel):
    """Medication schema"""

    name: str
    dosage: str
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    prescribed_by: Optional[str] = None


class Procedure(BaseModel):
    """Procedure schema"""

    name: str
    date: str
    provider: Optional[str] = None
    notes: Optional[str] = None


class Vital(BaseModel):
    """Vital signs schema"""

    type: str
    value: str
    unit: str
    date: str


class LabResult(BaseModel):
    """Lab result schema"""

    test_name: str
    value: str
    unit: str
    reference_range: Optional[str] = None
    date: str
    abnormal: bool = False


class ExtractedData(BaseModel):
    """Extracted clinical data schema"""

    diagnoses: List[str] = []
    medications: List[Medication] = []
    procedures: List[Procedure] = []
    vitals: List[Vital] = []
    labs: List[LabResult] = []
    allergies: List[str] = []


class ExtractionResponse(BaseModel):
    """Clinical extraction response"""

    id: str
    case_id: str
    extracted_data: ExtractedData
    timeline: List[TimelineEvent]
    contradictions: List[Contradiction]
    summary: str
    executive_summary: Optional[str] = None  # Concise 5-10 bullet summary for PDFs
    created_at: datetime

    class Config:
        from_attributes = True

