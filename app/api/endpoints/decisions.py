"""Decision API endpoints"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_decision_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.decision_repository import DecisionRepository
from app.schemas.decision import DecisionCreate, DecisionUpdate, DecisionResponse
from app.models.decision import Decision
from app.models.case import Case
from app.models.user import User
from app.api.endpoints.auth import get_current_user

router = APIRouter()


@router.post("/{case_id}/decision", response_model=DecisionResponse)
async def create_decision(
    case_id: str,
    decision: DecisionCreate,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    decision_repository: DecisionRepository = Depends(get_decision_repository),
    current_user: User = Depends(get_current_user),
):
    """Create a new UM decision for a case"""
    # Check if case exists
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Check if decision already exists
    existing_decision = decision_repository.get_by_case_id(db, case_id)
    if existing_decision:
        raise HTTPException(
            status_code=400,
            detail="Decision already exists for this case. Use PUT to update.",
        )

    # Create new decision
    new_decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case_id,
        user_id=current_user.id,
        decision_type=decision.decision_type,
        sub_status=decision.sub_status,
        notes=decision.notes,
        decided_by=decision.decided_by,
        decided_at=datetime.now(timezone.utc),
    )

    # Mark case as reviewed
    case.is_reviewed = True
    case.reviewed_at = datetime.now(timezone.utc)
    case.reviewed_by = decision.decided_by
    case_repository.update(db, case)

    return decision_repository.create(db, new_decision)


@router.get("/{case_id}/decision", response_model=DecisionResponse)
async def get_decision(
    case_id: str,
    db: Session = Depends(get_db),
    decision_repository: DecisionRepository = Depends(get_decision_repository),
    current_user: User = Depends(get_current_user),
):
    """Get the decision for a case"""
    decision = decision_repository.get_by_case_id(db, case_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found for this case")

    return decision


@router.put("/{case_id}/decision", response_model=DecisionResponse)
async def update_decision(
    case_id: str,
    decision_update: DecisionUpdate,
    db: Session = Depends(get_db),
    decision_repository: DecisionRepository = Depends(get_decision_repository),
):
    """Update an existing decision"""
    decision = decision_repository.get_by_case_id(db, case_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found for this case")

    # Update fields
    if decision_update.decision_type is not None:
        decision.decision_type = decision_update.decision_type
    if decision_update.sub_status is not None:
        decision.sub_status = decision_update.sub_status
    if decision_update.notes is not None:
        decision.notes = decision_update.notes

    decision.updated_at = datetime.now(timezone.utc)

    return decision_repository.update(db, decision)


@router.post("/{case_id}/mark-reviewed")
async def mark_case_reviewed(
    case_id: str,
    reviewed_by: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
):
    """Mark a case as reviewed without making a decision"""
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.is_reviewed = True
    case.reviewed_at = datetime.now(timezone.utc)
    case.reviewed_by = reviewed_by

    case_repository.update(db, case)

    return {
        "message": "Case marked as reviewed",
        "case_id": case_id,
        "reviewed_by": reviewed_by,
    }
