"""Case file serving: page text and PDF URL/stream."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_case_file_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.services.pdf_service import pdf_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/cases/{case_id}/files/{file_id}/page/{page}")
async def get_file_page(
    case_id: str,
    file_id: str,
    page: int,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
):
    """Get text for specific page of a file."""
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_file = case_file_repository.get_by_case_and_file_id(db, case_id, file_id)
    if not case_file:
        raise HTTPException(status_code=404, detail="File not found")

    pdf_result = pdf_service.extract_text_from_pdf(case_file.file_path)
    page_text = ""
    for page_data in pdf_result.get("pages", []):
        if page_data.get("page_number") == page:
            page_text = page_data.get("text", "")
            break

    return {
        "file_id": file_id,
        "file_name": case_file.file_name,
        "page": page,
        "text": page_text,
        "total_pages": case_file.page_count,
        "pdf_url": f"/api/v1/cases/{case_id}/files/{file_id}/pdf",
    }


@router.get("/cases/{case_id}/files/{file_id}/pdf")
async def get_file_pdf(
    case_id: str,
    file_id: str,
    use_proxy: bool = False,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
):
    """
    Get PDF file - supports both pre-signed URLs and backend streaming.

    For S3:
    - By default: Returns pre-signed URL for direct browser access (requires S3 CORS).
    - If use_proxy=true: Streams through backend to avoid CORS issues.

    For local: Always streams through backend.
    """
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_file = case_file_repository.get_by_case_and_file_id(db, case_id, file_id)
    if not case_file:
        raise HTTPException(status_code=404, detail="File not found")

    if not case_file.file_path:
        raise HTTPException(status_code=404, detail="File path not found")

    if settings.STORAGE_TYPE == "s3":
        if use_proxy:
            from app.services.s3_storage_service import s3_storage_service
            try:
                pdf_content = s3_storage_service.get_file_content(case_file.file_path)
                return Response(
                    content=pdf_content,
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'inline; filename="{case_file.file_name}"',
                        "Content-Length": str(len(pdf_content)),
                        "Cache-Control": "private, max-age=3600",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "*",
                    },
                )
            except Exception as e:
                logger.error(f"Failed to retrieve PDF from S3 for {case_file.file_path}: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve PDF document.")
        else:
            from app.services.s3_storage_service import s3_storage_service
            try:
                presigned_url = s3_storage_service.get_file_url(
                    case_file.file_path, expires_in=3600
                )
                return {
                    "url": presigned_url,
                    "file_name": case_file.file_name,
                    "expires_in": 3600,
                    "proxy_url": f"/api/v1/cases/{case_id}/files/{file_id}/pdf?use_proxy=true",
                }
            except Exception as e:
                logger.error(f"Failed to generate pre-signed URL for {case_file.file_path}: {e}")
                raise HTTPException(status_code=500, detail="Failed to generate PDF access URL.")

    if not os.path.exists(case_file.file_path):
        raise HTTPException(status_code=404, detail="Source file not found on server.")

    return FileResponse(
        path=case_file.file_path,
        media_type="application/pdf",
        filename=case_file.file_name,
    )
