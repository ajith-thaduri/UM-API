"""Contradiction evidence source endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_extraction_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.extraction_repository import ExtractionRepository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/contradiction-evidence/{case_id}/{contradiction_id}")
async def get_contradiction_sources(
    case_id: str,
    contradiction_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get sources for a contradiction."""
    logger.info(f"Fetching contradiction sources for case_id={case_id}, contradiction_id={contradiction_id}")

    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    extraction = extraction_repository.get_by_case_id(db, case_id)

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    if not extraction.contradictions:
        raise HTTPException(status_code=404, detail="Contradictions not found")

    if not isinstance(extraction.contradictions, list):
        raise HTTPException(status_code=404, detail="Contradictions format error")

    contradiction = None
    for c in extraction.contradictions:
        if isinstance(c, dict) and c.get("id") == contradiction_id:
            contradiction = c
            break

    if not contradiction:
        logger.warning(
            f"Contradiction ID {contradiction_id} not found. "
            f"Available IDs: {[c.get('id') for c in extraction.contradictions if isinstance(c, dict)]}"
        )
        raise HTTPException(status_code=404, detail="Contradiction not found")

    sources = []
    source_mapping = extraction.source_mapping or {}
    contradiction_sources = contradiction.get("sources", [])

    if isinstance(contradiction_sources, list):
        for source in contradiction_sources:
            if not isinstance(source, dict):
                continue
            source_file = source.get("file")
            source_page = source.get("page")

            if source_file and source_page:
                file_id = None
                files_list = source_mapping.get("files", [])
                if isinstance(files_list, list):
                    for file_info in files_list:
                        if (
                            isinstance(file_info, dict)
                            and file_info.get("file_name") == source_file
                        ):
                            file_id = file_info.get("id")
                            break

                file_page_mapping = source_mapping.get("file_page_mapping", {})
                if (
                    file_id
                    and isinstance(file_page_mapping, dict)
                    and file_id in file_page_mapping
                ):
                    page_mapping = file_page_mapping[file_id]
                    if isinstance(page_mapping, dict):
                        page_text = page_mapping.get(source_page) or page_mapping.get(str(source_page), "")
                        sources.append({
                            "file_name": source_file,
                            "file_id": file_id,
                            "page": source_page,
                            "snippet": page_text[:500] if page_text else "",
                            "full_text": page_text,
                            "bbox": source.get("bbox"),
                            "term": source.get("term"),
                        })

    return {"contradiction": contradiction, "sources": sources}
