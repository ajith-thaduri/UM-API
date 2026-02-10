"""Extractions API endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_extraction_repository
from app.repositories.extraction_repository import ExtractionRepository

router = APIRouter()


@router.get("/{case_id}")
async def get_extraction(
    case_id: str,
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get clinical extraction for a case"""
    extraction = extraction_repository.get_by_case_id(db, case_id)
    
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="Extraction not found for this case",
        )
    
    return extraction


@router.get("/{case_id}/timeline")
async def get_timeline(
    case_id: str,
    level: str = Query("detailed", description="Timeline level: 'summary' for major events only, 'detailed' for all events"),
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """
    Get clinical timeline for a case
    
    Args:
        level: "summary" for major events only, "detailed" for all events (default: "detailed")
    """
    extraction = extraction_repository.get_by_case_id(db, case_id)
    
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="Timeline not found for this case",
        )
    
    # If timelines don't exist, generate them
    if not extraction.timeline and extraction.extracted_data:
        from app.services.timeline_service import timeline_service
        timeline_result = timeline_service.build_timeline(
            extraction.extracted_data, "", db=db, case_id=case_id, user_id=extraction.user_id
        )
        extraction.timeline = timeline_result.get("detailed", [])
        extraction.timeline_summary = timeline_result.get("summary", [])
        db.commit()
    
    # Return the requested level
    if level == "summary":
        timeline_data = extraction.timeline_summary or []
    else:
        timeline_data = extraction.timeline or []
    
    return {
        "timeline": timeline_data,
        "level": level,
        "summary_count": len(extraction.timeline_summary or []),
        "detailed_count": len(extraction.timeline or [])
    }


@router.get("/{case_id}/timelines")
async def get_timelines(
    case_id: str,
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get both summary and detailed timelines for a case"""
    extraction = extraction_repository.get_by_case_id(db, case_id)
    
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="Timelines not found for this case",
        )
    
    # If timelines don't exist, generate them
    if not extraction.timeline and extraction.extracted_data:
        from app.services.timeline_service import timeline_service
        timeline_result = timeline_service.build_timeline(
            extraction.extracted_data, "", db=db, case_id=case_id, user_id=extraction.user_id
        )
        extraction.timeline = timeline_result.get("detailed", [])
        extraction.timeline_summary = timeline_result.get("summary", [])
        db.commit()
    
    return {
        "summary": extraction.timeline_summary or [],
        "detailed": extraction.timeline or []
    }


@router.get("/{case_id}/contradictions")
async def get_contradictions(
    case_id: str,
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get contradictions detected for a case"""
    extraction = extraction_repository.get_by_case_id(db, case_id)
    
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="Contradictions not found for this case",
        )
    
    return {"contradictions": extraction.contradictions or []}


@router.get("/{case_id}/summary")
async def get_summary(
    case_id: str,
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get summary for a case"""
    extraction = extraction_repository.get_by_case_id(db, case_id)
    
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="Summary not found for this case",
        )
    
    return {
        "case_id": case_id,
        "summary": extraction.summary or "Summary not yet generated",
    }

