"""Analytics API schemas"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class TimeToReviewMetrics(BaseModel):
    """Time-to-review metrics"""
    average_hours: float
    min_hours: float
    max_hours: float
    median_hours: float
    total_cases: int


class CasesPerDayDataPoint(BaseModel):
    """Cases per day data point"""
    date: str
    cases_reviewed: int
    cases_uploaded: int


class EvidenceClickByType(BaseModel):
    """Evidence clicks by type"""
    timeline: int = 0
    medication: int = 0
    lab: int = 0
    diagnosis: int = 0
    chunk: int = 0


class EvidenceClickByCase(BaseModel):
    """Evidence clicks by case"""
    case_id: str
    case_number: str
    clicks: int


class EvidenceClickTimeSeriesPoint(BaseModel):
    """Evidence click time series data point"""
    date: str
    clicks: int


class RecentEvidenceClick(BaseModel):
    """Recent evidence click"""
    id: str
    case_id: str
    case_number: str
    entity_type: str
    entity_id: str
    source_type: str
    clicked_at: str


class EvidenceClickStats(BaseModel):
    """Evidence click statistics"""
    total_clicks: int
    by_type: Dict[str, int]
    by_case: List[EvidenceClickByCase]
    time_series: List[EvidenceClickTimeSeriesPoint]
    recent_clicks: List[RecentEvidenceClick]


class TimeToReviewResponse(BaseModel):
    """Time-to-review metrics response"""
    metrics: TimeToReviewMetrics
    date_range: Dict[str, str]


class CasesPerDayResponse(BaseModel):
    """Cases per day response"""
    data: List[CasesPerDayDataPoint]
    date_range: Dict[str, str]


class EvidenceClicksResponse(BaseModel):
    """Evidence clicks response"""
    stats: EvidenceClickStats
    date_range: Dict[str, str]


class ReviewMetricsResponse(BaseModel):
    """Comprehensive review metrics response"""
    time_to_review: TimeToReviewMetrics
    cases_per_day: List[CasesPerDayDataPoint]
    evidence_clicks: EvidenceClickStats
    today_cases_reviewed: int
    date_range: Dict[str, str]

