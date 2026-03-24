"""Case schemas"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class CaseStatus(str, Enum):
    """Case status enumeration"""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    TIMELINE_BUILDING = "timeline_building"
    READY = "ready"
    REVIEWED = "reviewed"
    FAILED = "failed"


class Priority(str, Enum):
    """Case priority enumeration"""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class CaseCreate(BaseModel):
    """Schema for creating a new case"""

    patient_id: str = Field(..., description="Patient identifier")
    patient_name: str = Field(..., description="Patient name")
    case_number: str = Field(..., description="Unique case number")
    priority: Priority = Field(default=Priority.NORMAL, description="Case priority")


class ReviewStatus(str, Enum):
    """Review status enumeration (from decision)"""
    
    NOT_REVIEWED = "not_reviewed"
    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"
    NEEDS_CLARIFICATION = "needs_clarification"


class CaseResponse(BaseModel):
    """Schema for case response"""

    id: str
    patient_id: str
    patient_name: str
    case_number: str
    status: CaseStatus
    priority: Priority
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    record_count: int
    page_count: int
    live_version_id: Optional[str] = None
    latest_version_number: int = 1
    processing_version_id: Optional[str] = None
    # Review status from decision
    review_status: ReviewStatus = ReviewStatus.NOT_REVIEWED
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    """Response after uploading a case"""

    case_id: str
    status: str
    message: str

