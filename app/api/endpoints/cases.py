"""Cases API endpoints"""

from typing import List
import uuid
import logging
import shutil
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_case_file_repository, get_extraction_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.extraction_repository import ExtractionRepository, extraction_repository
from app.services.pgvector_service import pgvector_service
from app.api.endpoints.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
from app.schemas.case import CaseResponse, UploadResponse
from app.models.case import Case, CaseStatus, Priority
from app.models.case_file import CaseFile
from app.services.storage_service import storage_service
from app.services.case_processor import case_processor
from app.services.pdf_service import pdf_service
from app.services.pdf_generator_service import pdf_generator_service
# Use fpdf2 for PDF generation when available; resolve lazily so tests can load app without fpdf2 installed
def _get_pdf_generator_active():
    try:
        from app.services.pdf_generator_service_fpdf2 import pdf_generator_service_fpdf2
        logger.info("PDF generator: using fpdf2 (new)")
        return pdf_generator_service_fpdf2
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning(
            "PDF generator: fpdf2 not available (%s), using ReportLab fallback. "
            "Install fpdf2 and markdown-it-py in the deploy environment to use the new PDF.",
            e,
        )
        return pdf_generator_service


from app.core.config import settings

# Disable trailing slash redirect
router = APIRouter(redirect_slashes=False)


async def _get_cases_impl(
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
    status: str,
    priority: str,
    search: str,
    date_range: str,
    user_id: str,
    db: Session,
    case_repository: CaseRepository,
):
    """Internal implementation for get cases"""
    from app.schemas.case import ReviewStatus
    
    skip = (page - 1) * page_size
    cases, total = case_repository.get_with_filters(
        db=db,
        user_id=user_id,
        status=status,
        priority=priority,
        search=search,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=page_size,
    )

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    # Build response items with review_status from decision
    items = []
    for case in cases:
        case_dict = {
            "id": case.id,
            "patient_id": case.patient_id,
            "patient_name": case.patient_name,
            "case_number": case.case_number,
            "status": case.status,
            "priority": case.priority,
            "uploaded_at": case.uploaded_at,
            "processed_at": case.processed_at,
            "assigned_to": None,
            "record_count": case.record_count,
            "page_count": case.page_count,
            "review_status": ReviewStatus.NOT_REVIEWED,
            "reviewed_by": case.reviewed_by,
            "reviewed_at": case.reviewed_at,
        }
        
        # Get review status from decision if exists
        if case.decision:
            decision_type = case.decision.decision_type.value if hasattr(case.decision.decision_type, 'value') else str(case.decision.decision_type)
            # Map decision_type to review_status
            status_mapping = {
                "approved": ReviewStatus.APPROVED,
                "denied": ReviewStatus.DENIED,
                "pending": ReviewStatus.PENDING,
                "needs_clarification": ReviewStatus.NEEDS_CLARIFICATION,
            }
            case_dict["review_status"] = status_mapping.get(decision_type.lower(), ReviewStatus.NOT_REVIEWED)
            case_dict["reviewed_by"] = case.decision.decided_by
            case_dict["reviewed_at"] = case.decision.decided_at
        
        items.append(CaseResponse.model_validate(case_dict))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": total_pages,
    }


@router.get("")
@router.get("/")
async def get_cases(
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "uploaded_at",
    sort_order: str = "desc",
    status: str = None,
    priority: str = None,
    search: str = None,
    date_range: str = None,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """Get all cases with pagination and filtering for current user"""
    return await _get_cases_impl(page, page_size, sort_by, sort_order, status, priority, search, date_range, current_user.id, db, case_repository)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """Get a specific case by ID for current user"""
    from app.schemas.case import ReviewStatus
    
    case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Map to dict to add extra fields
    case_dict = {
        "id": case.id,
        "patient_id": case.patient_id,
        "patient_name": case.patient_name,
        "case_number": case.case_number,
        "status": case.status,
        "priority": case.priority,
        "uploaded_at": case.uploaded_at,
        "processed_at": case.processed_at,
        "assigned_to": None,
        "record_count": case.record_count,
        "page_count": case.page_count,
        "review_status": ReviewStatus.NOT_REVIEWED,
        "reviewed_by": case.reviewed_by,
        "reviewed_at": case.reviewed_at,
    }
    
    # Get review status from decision if exists
    if case.decision:
        decision_type = case.decision.decision_type.value if hasattr(case.decision.decision_type, 'value') else str(case.decision.decision_type)
        # Map decision_type to review_status
        status_mapping = {
            "approved": ReviewStatus.APPROVED,
            "denied": ReviewStatus.DENIED,
            "pending": ReviewStatus.PENDING,
            "needs_clarification": ReviewStatus.NEEDS_CLARIFICATION,
        }
        case_dict["review_status"] = status_mapping.get(decision_type.lower(), ReviewStatus.NOT_REVIEWED)
        case_dict["reviewed_by"] = case.decision.decided_by
        case_dict["reviewed_at"] = case.decision.decided_at
    
    return CaseResponse.model_validate(case_dict)


@router.post("/upload", response_model=UploadResponse)
async def upload_case(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    patient_id: str = Form(...),
    patient_name: str = Form(...),
    case_number: str = Form(...),
    priority: str = Form("normal"),
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
    current_user: User = Depends(get_current_user),
):
    """Upload a new medical record case with multiple files"""
    try:
        # Validate files
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="At least one file is required")
        
        # Validate all files are PDFs
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="All files must have a filename")
            
            # Validate file extension
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Only PDF files are supported")
            
            # Validate MIME type if available
            if hasattr(file, 'content_type') and file.content_type:
                if file.content_type != 'application/pdf':
                    raise HTTPException(status_code=400, detail=f"File {file.filename} is not a valid PDF (MIME type: {file.content_type})")
            
            # File size validation happens in storage_service.save_case_files()

        # Check if case number already exists for this user
        existing_case = case_repository.get_by_case_number(db, case_number, current_user.id)
        if existing_case:
            raise HTTPException(status_code=400, detail="Case number already exists")

        # Validate priority
        try:
            priority_enum = Priority[priority.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}. Must be one of: urgent, high, normal, low")

        # Generate case ID
        case_id = str(uuid.uuid4())

        # Save all files using storage service (with user_id)
        file_results = await storage_service.save_case_files(case_id, files, user_id=current_user.id)
        
        # Analyze files to detect document types
        from app.services.pdf_analyzer_service import pdf_analyzer_service
        file_paths = [path for path, _, _ in file_results]
        analysis_result = await pdf_analyzer_service.analyze_for_upload(file_paths)
        
        # Guardrail check: Reject non-medical documents if guardrail is enabled
        if settings.ENABLE_MEDICAL_GUARDRAIL:
            invalid_files = []
            for file_analysis in analysis_result.files:
                if file_analysis.detected_type.startswith("non_medical_"):
                    category = file_analysis.detected_type.replace("non_medical_", "").title()
                    invalid_files.append(f"{file_analysis.file_name} (detected as {category})")
            
            if invalid_files:
                # Clean up uploaded files before rejecting
                try:
                    for path, _, _ in file_results:
                        # Attempt to delete from storage (if supported)
                        pass  # Storage cleanup can be added here if needed
                except Exception as e:
                    logger.warning(f"Failed to cleanup rejected files: {e}")
                
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid document type(s): {', '.join(invalid_files)}. Please upload valid medical records (e.g., Discharge Summary, Lab Report)."
                )
        
        # Create mapping of filename to detected type
        file_types_map = {}
        for file_analysis in analysis_result.files:
            # Match by filename (extract just the name from path if needed)
            file_name = file_analysis.file_name
            file_types_map[file_name] = file_analysis.detected_type
        
        # Create case record
        new_case = Case(
            id=case_id,
            patient_id=patient_id,
            patient_name=patient_name,
            case_number=case_number,
            status=CaseStatus.UPLOADED,
            priority=priority_enum,
            user_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            record_count=len(files),
            page_count=0,  # Will be updated after processing
        )

        # Create case using repository
        new_case = case_repository.create(db, new_case)
        
        # Create CaseFile records for each uploaded file
        total_pages = 0
        for idx, (file_path, file_size, original_filename) in enumerate(file_results):
            # Get page count from PDF
            page_count = pdf_service.count_pages(file_path)
            total_pages += page_count
            
            # Get detected document type from analysis
            detected_type = file_types_map.get(original_filename, None)
            
            case_file = CaseFile(
                id=str(uuid.uuid4()),
                case_id=case_id,
                user_id=current_user.id,
                file_name=original_filename,
                file_path=file_path,
                file_size=file_size,
                page_count=page_count,
                file_order=idx,
                document_type=detected_type,  # Save detected document type
                uploaded_at=datetime.utcnow()
            )
            case_file_repository.create(db, case_file)
        
        # Update case page count
        new_case.page_count = total_pages
        case_repository.update(db, new_case)

        # Trigger background processing (async)
        async def process_case_async():
            await case_processor.process_case(case_id)
        background_tasks.add_task(process_case_async)

        return UploadResponse(
            case_id=case_id,
            status="uploaded",
            message=f"Case uploaded successfully with {len(files)} file(s). Processing will begin shortly.",
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Rollback on any error
        db.rollback()
        logger.error(f"Error uploading case: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{case_id}/generate-summary")
async def generate_summary(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """Trigger summary generation for a case"""
    case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Trigger reprocessing (no db session passed - will create new one)
    # Trigger background processing (async)
    async def process_case_async():
        await case_processor.process_case(case_id)
    background_tasks.add_task(process_case_async)

    return {
        "message": "Summary regeneration started",
        "case_id": case_id,
    }


@router.post("/{case_id}/retry")
async def retry_processing(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """Retry processing for a failed case"""
    case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Reset status
    case.status = CaseStatus.UPLOADED
    case.processed_at = None
    case_repository.update(db, case)

    # Trigger reprocessing (no db session passed - will create new one)
    # Trigger background processing (async)
    async def process_case_async():
        await case_processor.process_case(case_id)
    background_tasks.add_task(process_case_async)

    return {
        "message": "Processing retry initiated",
        "case_id": case_id,
    }


@router.get("/{case_id}/status")
async def get_case_status(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """Get processing status of a case"""
    case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return {
        "case_id": case_id,
        "status": case.status.value,
        "uploaded_at": case.uploaded_at,
        "processed_at": case.processed_at,
    }


@router.get("/{case_id}/files")
async def get_case_files(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
    current_user: User = Depends(get_current_user),
):
    """Get all files for a case"""
    case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    files = case_file_repository.get_by_case_id(db, case_id, ordered=True)
    
    return {
        "case_id": case_id,
        "files": [
            {
                "id": f.id,
                "file_name": f.file_name,
                "file_size": f.file_size,
                "page_count": f.page_count,
                "file_order": f.file_order,
                "document_type": f.document_type,  # Include detected document type
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None
            }
            for f in files
        ]
    }


@router.delete("/{case_id}")
async def delete_case(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
    current_user: User = Depends(get_current_user),
):
    """Delete a case and all associated data including FAISS embeddings"""
    case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    deleted_chunks = 0
    
    try:
        # Get all files for cleanup
        files = case_file_repository.get_by_case_id(db, case_id, ordered=False)
        
        # Parallelize independent deletion operations (Vector store and S3 can run in parallel)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def delete_vectors():
            """Delete Vector chunks (PgVector)"""
            try:
                return pgvector_service.delete_case_chunks(case_id, user_id=current_user.id)
            except Exception as e:
                logger.warning(f"Failed to delete vector chunks for case {case_id}: {e}")
                return 0
        
        def delete_storage_files():
            """Delete storage files (S3 or local)"""
            try:
                if settings.STORAGE_TYPE == "s3":
                    # Delete from S3
                    from app.services.s3_storage_service import s3_storage_service
                    return s3_storage_service.delete_case_files(case_id, user_id=current_user.id)
                else:
                    # Delete local files
                    deleted = 0
                    for file in files:
                        try:
                            if file.file_path:
                                import os
                                if os.path.exists(file.file_path):
                                    os.remove(file.file_path)
                                    deleted += 1
                        except (OSError, PermissionError) as e:
                            logger.warning(f"Failed to delete file {file.file_path}: {e}")
                    
                    # Delete case directory if it exists
                    try:
                        case_dir = storage_service.get_case_directory(case_id, user_id=current_user.id)
                        if hasattr(case_dir, 'exists') and case_dir.exists():
                            shutil.rmtree(case_dir)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Failed to delete case directory: {e}")
                    
                    return deleted
            except (OSError, PermissionError, ValueError) as e:
                logger.warning(f"Failed to delete files from storage: {e}")
                return 0
        
        # Run Vector and storage deletions in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(delete_vectors)
            storage_future = executor.submit(delete_storage_files)
            
            # Wait for both to complete
            deleted_chunks = vector_future.result()
            storage_deleted = storage_future.result()
            
            if deleted_chunks > 0:
                logger.info(f"Deleted {deleted_chunks} chunks from PgVector for case {case_id}")
            if storage_deleted > 0:
                logger.info(f"Deleted {storage_deleted} files from storage for case {case_id}")
        
        # Delete document chunks from database (already handled by pgvector_service, but redundant safety)
        try:
            from app.models.document_chunk import DocumentChunk
            db.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).delete()
        except Exception as e:
            logger.warning(f"Failed to delete document chunks: {e}")
        
        # Delete extraction data if exists
        try:
            extraction_repository.delete_by_case_id(db, case_id)
        except Exception as e:
            logger.warning(f"Failed to delete extraction: {e}")
        
        # Delete dashboard data if exists
        try:
            from app.models.dashboard import DashboardSnapshot, FacetResult, SourceLink
            # Delete source links first (foreign key constraint)
            db.query(SourceLink).filter(SourceLink.case_id == case_id).delete()
            # Delete facet results
            db.query(FacetResult).filter(FacetResult.case_id == case_id).delete()
            # Delete dashboard snapshots
            db.query(DashboardSnapshot).filter(DashboardSnapshot.case_id == case_id).delete()
        except Exception as e:
            logger.warning(f"Failed to delete dashboard data: {e}")
        
        # Delete case files from database
        for file in files:
            db.delete(file)
        
        # Delete the case itself
        db.delete(case)
        db.commit()
        
        logger.info(f"Successfully deleted case {case_id} with {deleted_chunks} vector chunks")
        
        return {
            "message": "Case deleted successfully",
            "case_id": case_id,
            "vector_chunks_deleted": deleted_chunks,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting case {case_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete case: {str(e)}")


@router.get("/{case_id}/pdf")
async def generate_case_pdf(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user)
):
    """
    Generate PDF summary for a UM case
    
    Returns a PDF document with:
    - Cover page with case info and disclaimer
    - Case Overview
    - Clinical Timeline
    - Clinical Summary
    - Potential Missing Info
    - Source Index
    """
    try:
        # Get case and verify access
        case = case_repository.get_by_id(db, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        if case.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check case is ready
        if case.status != CaseStatus.READY:
            raise HTTPException(
                status_code=400,
                detail=f"Case is not ready for PDF generation. Current status: {case.status.value}"
            )
        
        # Get extraction
        extraction = extraction_repository.get_by_case_id(db, case_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Case extraction not found. Case may not be fully processed.")
        
        # Get case files
        case_files = db.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.user_id == current_user.id
        ).order_by(CaseFile.file_order).all()
        
        if not case_files:
            raise HTTPException(status_code=404, detail="No files found for this case")
        
        # Extract DOB from extracted_data if available
        patient_dob = None
        if extraction.extracted_data and isinstance(extraction.extracted_data, dict):
            patient_demographics = extraction.extracted_data.get('patient_demographics', {})
            if isinstance(patient_demographics, dict):
                patient_dob = patient_demographics.get('dob')
        
        # Generate PDF with user name
        generated_by = current_user.name or current_user.email
        try:
            pdf_bytes = _get_pdf_generator_active().generate_case_pdf(
                case=case,
                extraction=extraction,
                case_files=case_files,
                patient_dob=patient_dob,
                generated_by=generated_by
            )
        except Exception as e:
            logger.error(f"Error generating PDF for case {case_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")
        
        # Generate filename
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"UM_Case_{case.case_number}_{date_str}.pdf"
        
        # Return PDF response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating PDF for case {case_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{case_id}/json")
async def export_case_json(
    case_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
    current_user: User = Depends(get_current_user)
):
    """
    Export case data as structured JSON
    
    Returns a comprehensive JSON document with:
    - Case metadata
    - Case files information
    - Extracted clinical data
    - Timeline (summary and detailed)
    - Clinical summary
    - Contradictions/potential missing info
    - Source mappings
    """
    import json as json_lib
    
    try:
        # Get case and verify access
        case = case_repository.get_by_id(db, case_id, user_id=current_user.id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        # Get extraction
        extraction = extraction_repository.get_by_case_id(db, case_id, user_id=current_user.id)
        
        # Get case files
        case_files = case_file_repository.get_by_case_id(db, case_id)
        
        # Get decision if exists
        from app.repositories.decision_repository import DecisionRepository
        decision_repo = DecisionRepository()
        decision = decision_repo.get_by_case_id(db, case_id)
        
        # Build structured JSON response
        export_data = {
            "export_metadata": {
                "exported_at": datetime.utcnow().isoformat(),
                "exported_by": current_user.email,
                "case_id": case_id,
                "format_version": "1.0"
            },
            "case": {
                "id": case.id,
                "case_number": case.case_number,
                "patient_id": case.patient_id,
                "patient_name": case.patient_name,
                "status": case.status.value if hasattr(case.status, 'value') else str(case.status),
                "priority": case.priority.value if hasattr(case.priority, 'value') else str(case.priority),
                "uploaded_at": case.uploaded_at.isoformat() if case.uploaded_at else None,
                "processed_at": case.processed_at.isoformat() if case.processed_at else None,
                "record_count": case.record_count,
                "page_count": case.page_count,
            },
            "files": [
                {
                    "id": file.id,
                    "file_name": file.file_name,
                    "file_path": file.file_path,
                    "file_size": file.file_size,
                    "page_count": file.page_count,
                    "file_order": file.file_order,
                    "document_type": file.document_type,
                    "uploaded_at": file.uploaded_at.isoformat() if file.uploaded_at else None,
                }
                for file in case_files
            ],
            "extraction": {}
        }
        
        # Add extraction data if available
        if extraction:
            export_data["extraction"] = {
                "extracted_data": extraction.extracted_data,
                "timeline": {
                    "summary": extraction.timeline_summary,
                    "detailed": extraction.timeline,
                    "summary_count": len(extraction.timeline_summary) if extraction.timeline_summary else 0,
                    "detailed_count": len(extraction.timeline) if extraction.timeline else 0,
                },
                "summary": extraction.summary,
                "executive_summary": getattr(extraction, 'executive_summary', None),  # Concise 5-10 bullet summary
                "contradictions": extraction.contradictions,
                "source_mapping": extraction.source_mapping,
                "edited_sections": extraction.edited_sections,
                "created_at": extraction.created_at.isoformat() if extraction.created_at else None,
                "updated_at": extraction.updated_at.isoformat() if extraction.updated_at else None,
            }
        else:
            export_data["extraction"] = None
        
        # Add decision if exists
        if decision:
            export_data["decision"] = {
                "id": decision.id,
                "decision_type": decision.decision_type.value if hasattr(decision.decision_type, 'value') else str(decision.decision_type),
                "decision_date": decision.decision_date.isoformat() if decision.decision_date else None,
                "notes": decision.notes,
                "created_at": decision.created_at.isoformat() if decision.created_at else None,
            }
        else:
            export_data["decision"] = None
        
        # Convert to JSON string with pretty formatting
        json_content = json_lib.dumps(export_data, indent=2, default=str)
        
        # Generate filename
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"UM_Case_{case.case_number}_{date_str}.json"
        
        # Return JSON response
        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(json_content.encode('utf-8')))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error exporting JSON for case {case_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
