"""Pydantic schemas for Upload Agent API"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class ConversationStateEnum(str, Enum):
    """States in the upload conversation flow"""
    GREETING = "greeting"
    WAITING_FOR_FILES = "waiting_for_files"
    ANALYZING_FILES = "analyzing_files"
    CONFIRM_ANALYSIS = "confirm_analysis"
    COLLECTING_DATA = "collecting_data"
    REVIEW_SUMMARY = "review_summary"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class MessageTypeEnum(str, Enum):
    """Types of agent messages"""
    GREETING = "greeting"
    QUESTION = "question"
    CONFIRMATION = "confirmation"
    STATUS = "status"
    ERROR = "error"
    SUCCESS = "success"


# Request Schemas

class StartSessionRequest(BaseModel):
    """Request to start a new upload session"""
    pass  # No parameters needed


class SendMessageRequest(BaseModel):
    """Request to send a message to the agent"""
    session_id: str
    message: str


class ConfirmUploadRequest(BaseModel):
    """Request to confirm and start processing"""
    session_id: str


# Response Schemas

class QuickActionResponse(BaseModel):
    """Quick action button"""
    label: str
    value: str
    variant: str = "default"


class FileInfoResponse(BaseModel):
    """File information"""
    name: str
    pages: int
    type: str
    size: Optional[int] = None


class PatientInfoResponse(BaseModel):
    """Extracted patient information"""
    name: Optional[str] = None
    dob: Optional[str] = None
    mrn: Optional[str] = None
    gender: Optional[str] = None
    encounter_date: Optional[str] = None
    provider: Optional[str] = None
    facility: Optional[str] = None


class AgentMessageResponse(BaseModel):
    """Agent message response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    message: str
    type: MessageTypeEnum
    timestamp: str
    actions: List[QuickActionResponse] = []
    field: Optional[str] = None
    suggestions: List[str] = []
    extracted_data: Optional[Dict[str, Any]] = None
    files_info: Optional[List[FileInfoResponse]] = None
    progress: Optional[int] = None


class StartSessionResponse(BaseModel):
    """Response when starting a new session"""
    session_id: str
    message: AgentMessageResponse


class AnalyzeFilesResponse(BaseModel):
    """Response after analyzing uploaded files"""
    session_id: str
    message: AgentMessageResponse
    patient_info: PatientInfoResponse
    files: List[FileInfoResponse]
    total_pages: int
    extraction_confidence: float


class SendMessageResponse(BaseModel):
    """Response after sending a message"""
    session_id: str
    message: AgentMessageResponse
    state: ConversationStateEnum


class SessionStatusResponse(BaseModel):
    """Session status response"""
    session_id: str
    state: ConversationStateEnum
    patient_info: PatientInfoResponse
    case_number: Optional[str] = None
    priority: str = "normal"
    files: List[Dict[str, Any]] = []
    processing_status: Optional[str] = None
    processing_progress: int = 0
    case_id: Optional[str] = None


class ProcessingStatusResponse(BaseModel):
    """Processing status update"""
    session_id: str
    status: str
    progress: int
    message: AgentMessageResponse
    case_id: Optional[str] = None


class ConfirmUploadResponse(BaseModel):
    """Response after confirming upload"""
    session_id: str
    case_id: str
    message: AgentMessageResponse
    processing_started: bool = True


class UploadDraftSummaryResponse(BaseModel):
    """One resumable upload draft (no case linked yet)."""

    session_id: str
    updated_at: datetime
    state: ConversationStateEnum
    file_count: int
    patient_name_snippet: Optional[str] = None


class ResumeUploadSessionResponse(BaseModel):
    """Bootstrap payload to hydrate the upload UI without starting a new session."""

    session_id: str
    state: ConversationStateEnum
    patient_info: PatientInfoResponse
    messages: List[Dict[str, Any]]
    file_count: int = 0
    # Sanitized file list for the document vault (no storage paths).
    files: List[FileInfoResponse] = Field(default_factory=list)

