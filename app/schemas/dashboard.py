"""Schemas for dashboard orchestration and facets."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from app.models.dashboard import FacetStatus, FacetType


class FacetResultBase(BaseModel):
    case_id: str
    facet_type: FacetType
    status: FacetStatus
    content: Optional[Any] = None
    sources: Optional[Any] = None


class FacetResultCreate(FacetResultBase):
    snapshot_id: str


class FacetResultResponse(FacetResultBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class DashboardSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    case_id: str
    version: int
    status: FacetStatus
    error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    facets: List[FacetResultResponse]


class DashboardResponse(BaseModel):
    snapshot: DashboardSnapshotResponse
    facets: Dict[FacetType, FacetResultResponse]


class SourceLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    item_id: str
    file_id: Optional[str]
    file_name: Optional[str]
    page_number: Optional[int]
    snippet: Optional[str]
    full_text: Optional[str]

