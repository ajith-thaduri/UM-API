"""Decision schemas"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class DecisionType(str, Enum):
    """Decision type enumeration"""

    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"
    NEEDS_CLARIFICATION = "needs_clarification"


class DecisionCreate(BaseModel):
    """Schema for creating a new decision"""

    decision_type: DecisionType = Field(..., description="Type of UM decision")
    sub_status: Optional[str] = Field(None, description="Optional sub-status or reason")
    notes: Optional[str] = Field(None, description="Decision notes or justification")
    decided_by: str = Field(..., description="Name or ID of decision maker")


class DecisionUpdate(BaseModel):
    """Schema for updating a decision"""

    decision_type: Optional[DecisionType] = None
    sub_status: Optional[str] = None
    notes: Optional[str] = None


class DecisionResponse(BaseModel):
    """Schema for decision response"""

    id: str
    case_id: str
    decision_type: DecisionType
    sub_status: Optional[str] = None
    notes: Optional[str] = None
    decided_by: str
    decided_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True








