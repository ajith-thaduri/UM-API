"""Annotations API endpoints - Summary edits and case notes"""

import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import (
    get_case_repository,
    get_extraction_repository,
    get_note_repository,
)
from app.repositories.case_repository import CaseRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.note_repository import NoteRepository
from app.models.note import CaseNote
from app.models.user import User
from app.api.endpoints.auth import get_current_user

router = APIRouter()


class SummarySectionUpdate(BaseModel):
    """Schema for updating a summary section"""

    section_name: str
    content: str
    edited_by: str


@router.put("/extractions/{case_id}/summary/section")
async def update_summary_section(
    case_id: str,
    update: SummarySectionUpdate,
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Update a specific section of the summary"""
    extraction = extraction_repository.get_by_case_id(db, case_id)

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    # Initialize edited_sections if None
    if extraction.edited_sections is None:
        extraction.edited_sections = {}

    # Update the edited section
    extraction.edited_sections[update.section_name] = {
        "content": update.content,
        "edited_by": update.edited_by,
        "edited_at": datetime.now(timezone.utc).isoformat(),
    }

    # Rebuild the summary with edited section
    # For now, we'll store it as-is. In production, you'd reconstruct the full summary
    extraction.updated_at = datetime.now(timezone.utc)

    extraction_repository.update(db, extraction)

    return {
        "message": "Section updated successfully",
        "section_name": update.section_name,
        "edited_by": update.edited_by,
    }


@router.get("/extractions/{case_id}/summary/sections")
async def get_edited_sections(
    case_id: str,
    db: Session = Depends(get_db),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get all edited sections for a case"""
    extraction = extraction_repository.get_by_case_id(db, case_id)

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    return {
        "edited_sections": extraction.edited_sections or {},
    }


# Case Notes Endpoints


class NoteCreate(BaseModel):
    """Schema for creating a note"""

    text: str
    author: str


class NoteResponse(BaseModel):
    """Schema for note response"""

    id: str
    case_id: str
    author: str
    text: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/cases/{case_id}/notes", response_model=List[NoteResponse])
async def get_case_notes(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    note_repository: NoteRepository = Depends(get_note_repository),
):
    """Get all notes for a case"""
    # Verify case exists
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    notes = note_repository.get_by_case_id(db, case_id, ordered=True)
    return notes


@router.post("/cases/{case_id}/notes", response_model=NoteResponse)
async def create_case_note(
    case_id: str,
    note: NoteCreate,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    note_repository: NoteRepository = Depends(get_note_repository),
    current_user: User = Depends(get_current_user),
):
    """Create a new note for a case"""
    # Verify case exists
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    new_note = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case_id,
        user_id=current_user.id,
        author=note.author,
        text=note.text,
        created_at=datetime.now(timezone.utc),
    )

    return note_repository.create(db, new_note)


@router.delete("/cases/{case_id}/notes/{note_id}")
async def delete_case_note(
    case_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    note_repository: NoteRepository = Depends(get_note_repository),
):
    """Delete a note"""
    note = note_repository.get_by_id(db, note_id)

    if not note or note.case_id != case_id:
        raise HTTPException(status_code=404, detail="Note not found")

    note_repository.delete(db, note_id)

    return {"message": "Note deleted successfully", "note_id": note_id}
