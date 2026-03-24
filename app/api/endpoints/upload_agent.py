"""Upload Agent API endpoints for agentic upload experience"""

import uuid
import logging
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form, Body
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_case_file_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.services.upload_agent_service import upload_agent_service, ConversationState
from app.services.pdf_analyzer_service import pdf_analyzer_service
from app.services.storage_service import storage_service
from app.services.case_processor import case_processor
from app.services.pdf_service import pdf_service
from app.models.case import Case, CaseStatus, Priority
from app.models.case_file import CaseFile
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.upload_agent import (
    StartSessionResponse,
    AnalyzeFilesResponse,
    SendMessageRequest,
    SendMessageResponse,
    ConfirmUploadResponse,
    SessionStatusResponse,
    ProcessingStatusResponse,
    AgentMessageResponse,
    QuickActionResponse,
    FileInfoResponse,
    PatientInfoResponse,
    ConversationStateEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload/agent", tags=["upload-agent"])


@router.post("/start", response_model=StartSessionResponse)
async def start_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new upload session and return greeting message"""
    session_id, greeting = upload_agent_service.start_session(db=db, user_id=current_user.id)
    
    return StartSessionResponse(
        session_id=session_id,
        message=AgentMessageResponse(
            id=greeting.id,
            message=greeting.message,
            type=greeting.type,
            timestamp=greeting.timestamp,
            actions=[QuickActionResponse(**a.__dict__) for a in greeting.actions],
            field=greeting.current_field,
            suggestions=greeting.suggestions,
            extracted_data=greeting.extracted_data,
            files_info=None,
            progress=greeting.progress
        )
    )


@router.post("/analyze", response_model=AnalyzeFilesResponse)
async def analyze_files(
    session_id: str = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and analyze files, extract patient information"""
    # Validate session
    session = upload_agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please start a new session.")
    
    # Verify session belongs to user
    if hasattr(session, 'user_id') and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")
    
    # Validate files
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="At least one file is required")
    
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="All files must have a filename")
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Save files temporarily for analysis (with user_id)
        temp_case_id = f"temp_{session_id}"
        file_results = await storage_service.save_case_files(temp_case_id, files, user_id=current_user.id)
        
        # Extract file paths
        file_paths = [path for path, _, _ in file_results]
        
        # Analyze files for patient info
        analysis_result = await pdf_analyzer_service.analyze_for_upload(file_paths)
        
        # Update session with analysis
        agent_message = await upload_agent_service.handle_files_uploaded(db, session_id, analysis_result)
        
        # Update session with temp file paths
        session = upload_agent_service.get_session(db, session_id)
        files = list(session.files or [])
        for i, (path, size, name) in enumerate(file_results):
            if i < len(files):
                files[i]["temp_path"] = path
        session.files = files
        db.commit()
        
        return AnalyzeFilesResponse(
            session_id=session_id,
            message=AgentMessageResponse(
                id=agent_message.id,
                message=agent_message.message,
                type=agent_message.type,
                timestamp=agent_message.timestamp,
                actions=[QuickActionResponse(**a.__dict__) for a in agent_message.actions],
                field=agent_message.current_field,
                suggestions=agent_message.suggestions,
                extracted_data=agent_message.extracted_data,
                files_info=[FileInfoResponse(**f) for f in (agent_message.files_info or [])],
                progress=agent_message.progress
            ),
            patient_info=PatientInfoResponse(**analysis_result.patient_info.to_dict()),
            files=[
                FileInfoResponse(
                    name=f.file_name,
                    pages=f.page_count,
                    type=f.detected_type,
                    size=f.file_size
                )
                for f in analysis_result.files
            ],
            total_pages=analysis_result.total_pages,
            extraction_confidence=analysis_result.extraction_confidence
        )
        
    except Exception as e:
        logger.error(f"Error analyzing files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing files: {str(e)}")


@router.post("/message", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message to the agent and get response"""
    session = upload_agent_service.get_session(db, request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please start a new session.")
    
    # Verify session belongs to user
    if hasattr(session, 'user_id') and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")
    
    agent_message = await upload_agent_service.process_message(db, request.session_id, request.message)
    
    # Get updated session state
    session = upload_agent_service.get_session(db, request.session_id)
    
    return SendMessageResponse(
        session_id=request.session_id,
        message=AgentMessageResponse(
            id=agent_message.id,
            message=agent_message.message,
            type=agent_message.type,
            timestamp=agent_message.timestamp,
            actions=[QuickActionResponse(**a.__dict__) for a in agent_message.actions],
            field=agent_message.current_field,
            suggestions=agent_message.suggestions,
            extracted_data=agent_message.extracted_data,
            files_info=[FileInfoResponse(**f) for f in (agent_message.files_info or [])] if agent_message.files_info else None,
            progress=agent_message.progress
        ),
        state=ConversationStateEnum(session.state)
    )


@router.post("/confirm", response_model=ConfirmUploadResponse)
async def confirm_upload(
    session_id: str = Body(..., embed=True),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
    current_user: User = Depends(get_current_user),
):
    """Confirm the upload and start processing"""
    session = upload_agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please start a new session.")
    
    # Verify session belongs to user
    if hasattr(session, 'user_id') and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")
    
    # Get session data for case creation
    case_data = upload_agent_service.get_session_data_for_case(db, session_id)
    if not case_data:
        raise HTTPException(status_code=400, detail="Session data incomplete")
    
    # Validate required fields
    if not case_data.get("patient_name"):
        raise HTTPException(status_code=400, detail="Patient name is required")
    if not case_data.get("case_number"):
        raise HTTPException(status_code=400, detail="Case number is required")
    
    # Check if case number already exists for this user
    existing_case = case_repository.get_by_case_number(db, case_data["case_number"], current_user.id)
    if existing_case:
        raise HTTPException(status_code=400, detail="Case number already exists")
    
    try:
        # Generate case ID
        case_id = str(uuid.uuid4())
        
        # Parse priority
        priority_str = case_data.get("priority", "normal").upper()
        try:
            priority_enum = Priority[priority_str]
        except KeyError:
            priority_enum = Priority.NORMAL
        
        # Move temp files to permanent location
        temp_case_id = f"temp_{session_id}"
        new_file_results = []
        
        from app.core.config import settings
        from pathlib import Path
        import shutil
        from app.services.s3_storage_service import s3_storage_service
        
        files_list = case_data.get("files", [])
        logger.info(f"Processing {len(files_list)} files for case {case_id}, storage type: {settings.STORAGE_TYPE}")
        
        if not files_list:
            logger.error(f"No files found in case_data for session {session_id}")
            raise HTTPException(status_code=400, detail="No files found in session. Please upload files first.")
        
        for file_info in files_list:
            temp_path = file_info.get("temp_path") or file_info.get("path")
            logger.info(f"Processing file: {file_info.get('name', 'unknown')}, temp_path: {temp_path}")
            if not temp_path:
                logger.warning(f"No temp_path found for file: {file_info.get('name', 'unknown')}")
                continue

            # Resolve content based on storage type and whether temp_path is an S3 key
            file_content: bytes | None = None
            temp_file_path = Path(temp_path)

            if settings.STORAGE_TYPE == "s3":
                try:
                    # Check if temp_path is an S3 key (starts with "users/" or "cases/")
                    if temp_path.startswith("users/") or temp_path.startswith("cases/"):
                        # temp file already in S3
                        file_content = s3_storage_service.get_file_content(temp_path)
                        logger.info(f"Downloaded temp file from S3: {temp_path}")
                    elif temp_file_path.exists():
                        # Fallback: local temp file (shouldn't happen in S3 mode, but handle gracefully)
                        file_content = temp_file_path.read_bytes()
                        logger.info(f"Loaded temp file from local path (S3 mode): {temp_file_path}")
                    else:
                        logger.warning(f"Temp file not found (S3 mode): {temp_path}")
                        continue
                except Exception as e:
                    logger.error(f"Failed to read temp file {temp_path}: {e}", exc_info=True)
                    continue
            else:
                # local storage
                if temp_file_path.exists():
                    file_content = temp_file_path.read_bytes()
                else:
                    logger.warning(f"Temp file does not exist: {temp_file_path}")
                    continue

            # Create a simple wrapper that mimics UploadFile interface
            class FileWrapper:
                def __init__(self, content: bytes, filename: str):
                    self._content = content
                    self.filename = filename
                    self.content_type = "application/pdf"
                
                async def read(self):
                    return self._content
            
            file_wrapper = FileWrapper(file_content, file_info["name"])

            if settings.STORAGE_TYPE == "s3":
                try:
                    s3_key, file_size, filename = await storage_service.save_case_file(
                        case_id=case_id,
                        file=file_wrapper,
                        file_id=str(uuid.uuid4()),
                        user_id=current_user.id
                    )
                    logger.info(f"Successfully saved file to S3: {s3_key}, size: {file_size} bytes")
                    new_file_results.append((s3_key, file_size, filename))
                except Exception as e:
                    logger.error(f"Failed to save file {file_info.get('name')} to S3: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Failed to save file to S3: {str(e)}")
            else:
                # For local storage: Move file from temp to permanent location
                case_dir = storage_service.get_case_directory(case_id, user_id=current_user.id)
                if isinstance(case_dir, str):
                    case_dir = Path(case_dir)
                case_dir.mkdir(parents=True, exist_ok=True)
                
                new_path = case_dir / file_info["name"]
                
                # Copy file (move might fail across different drives)
                with open(new_path, "wb") as f:
                    f.write(file_content)
                new_file_results.append((str(new_path), file_info.get("size", 0), file_info["name"]))
        
        # Clean up temp files
        try:
            if settings.STORAGE_TYPE == "local":
                temp_dir = storage_service.get_case_directory(temp_case_id, user_id=current_user.id)
                if isinstance(temp_dir, str):
                    temp_dir = Path(temp_dir)
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            else:
                # For S3, clean up temp files individually
                from app.services.s3_storage_service import s3_storage_service
                for file_info in case_data.get("files", []):
                    temp_path = file_info.get("temp_path") or file_info.get("path")
                    if temp_path and (temp_path.startswith("users/") or temp_path.startswith("cases/")):
                        try:
                            # Delete from S3
                            client = s3_storage_service._get_client()
                            client.delete_object(
                                Bucket=s3_storage_service.bucket_name,
                                Key=temp_path
                            )
                            logger.info(f"Deleted temp file from S3: {temp_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete S3 temp file {temp_path}: {e}")
        except Exception as e:
            logger.warning(f"Failed to clean temp files: {e}")
        
        # Validate that we have files
        if not new_file_results:
            logger.error(f"No files were successfully saved for case {case_id}")
            raise HTTPException(status_code=400, detail="No files were successfully saved. Please check file uploads.")
        
        logger.info(f"Successfully processed {len(new_file_results)} files for case {case_id}")
        
        # Create case record
        new_case = Case(
            id=case_id,
            patient_id=case_data.get("patient_mrn") or str(uuid.uuid4())[:8],
            patient_name=case_data["patient_name"],
            case_number=case_data["case_number"],
            status=CaseStatus.UPLOADED,
            priority=priority_enum,
            user_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            record_count=len(new_file_results),
            page_count=0,
        )
        
        new_case = case_repository.create(db, new_case)
        logger.info(f"Created case record: {case_id}")
        
        # Create CaseFile records
        total_pages = 0
        # Get detected types from session files (if available from analysis)
        file_types_map = {}
        if session.files:
            for file_info in session.files:
                if file_info.get("name") and file_info.get("type"):
                    file_types_map[file_info["name"]] = file_info["type"]
        
        created_file_ids = []
        for idx, (file_path, file_size, original_filename) in enumerate(new_file_results):
            logger.info(f"Creating CaseFile record {idx+1}/{len(new_file_results)}: {original_filename}")
            page_count = pdf_service.count_pages(file_path)
            total_pages += page_count
            
            # Get detected document type from session analysis (if available)
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
            created_file_ids.append(case_file.id)
        
        # Update case page count
        new_case.page_count = total_pages
        case_repository.update(db, new_case)

        from app.services.case_version_service import create_version_for_new_case
        create_version_for_new_case(db, new_case, created_file_ids)
        
        # Update session with case ID
        session.case_id = case_id
        session.state = ConversationState.PROCESSING
        
        # Update agent status
        status_message = upload_agent_service.update_processing_status(
            db, session_id, "starting", 5, case_id
        )
        
        # Start background processing with status updates
        background_tasks.add_task(
            _process_with_status_updates,
            case_id,
            session_id
        )
        
        return ConfirmUploadResponse(
            session_id=session_id,
            case_id=case_id,
            message=AgentMessageResponse(
                id=status_message.id,
                message=status_message.message,
                type=status_message.type,
                timestamp=status_message.timestamp,
                actions=[QuickActionResponse(**a.__dict__) for a in status_message.actions],
                field=status_message.current_field,
                suggestions=status_message.suggestions,
                extracted_data=status_message.extracted_data,
                files_info=None,
                progress=status_message.progress
            ),
            processing_started=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error confirming upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating case: {str(e)}")


async def _process_with_status_updates(case_id: str, session_id: str):
    """Enqueue case to UM-Jobs (non-blocking). Falls back to in-process if Redis unavailable."""
    from app.db.session import SessionLocal
    from app.core.redis import enqueue_case_processing, get_arq_pool

    db = SessionLocal()
    try:
        # Update status to queued / extracting_text immediately
        upload_agent_service.update_processing_status(db, session_id, "extracting_text", 10)
        logger.info(f"Starting processing for case {case_id}")

        # Get request metadata from session (stored for UM-Jobs to use if needed)
        session = upload_agent_service.get_session(db, session_id)
        user_id = session.user_id if session else None

        # Try to enqueue to UM-Jobs first (non-blocking)
        case_repository = CaseRepository()
        case_row = case_repository.get_by_id(db, case_id)
        cv_id = case_row.live_version_id if case_row else None
        if not cv_id:
            logger.error("Case %s has no live_version_id — cannot enqueue", case_id)
            return

        job_id = await enqueue_case_processing(case_id, user_id or "", cv_id)

        if job_id:
            # Enqueued successfully — UM-Jobs will update Case.status when done
            logger.info(f"Case {case_id} enqueued to UM-Jobs (job_id={job_id})")
            upload_agent_service.update_processing_status(db, session_id, "queued", 15, case_id)
            return

        # Fallback: Redis/ARQ unavailable — run in-process (original behaviour)
        logger.warning(f"ARQ unavailable — processing case {case_id} in-process (fallback)")
        request_metadata = None
        if session and (session.request_type or session.requested_service or session.request_date):
            urgency_value = session.urgency if hasattr(session, 'urgency') and session.urgency else 'Routine'
            request_metadata = {
                "request_type": session.request_type or "Not specified",
                "requested_service": session.requested_service or "Not specified",
                "request_date": session.request_date or "Not specified",
                "urgency": urgency_value,
            }
            logger.info(f"Passing request metadata to process_case: {request_metadata}")

        result = await case_processor.process_case(case_id, None, request_metadata)
        
        # Check result
        if result and result.get("success"):
            # Request metadata is now included in extraction during process_case
            # No need to update it separately
            
            # Update status: complete
            upload_agent_service.update_processing_status(db, session_id, "complete", 100, case_id)
            logger.info(f"Successfully processed case {case_id}")
            
            # Automatically trigger dashboard build after processing completes
            try:
                from app.services.orchestrator_service import build_orchestrator_service

                # Reuse repository from above (inner import would shadow CaseRepository and break line 474)
                case = case_repository.get_by_id(db, case_id)
                if case and case.user_id:
                    orchestrator = build_orchestrator_service()
                    logger.info(f"Auto-building dashboard for case {case_id}")
                    orchestrator.build_dashboard(db=db, case_id=case_id, user_id=case.user_id, force_reprocess=False)
                    db.commit()  # Ensure transaction is committed
                    logger.info(f"Dashboard built successfully for case {case_id}")
                else:
                    logger.warning(f"Case {case_id} not found or missing user_id, skipping dashboard build")
            except Exception as build_error:
                db.rollback()  # Rollback on error
                logger.warning(f"Failed to auto-build dashboard for case {case_id}: {build_error}", exc_info=True)
                # Don't fail the whole process if dashboard build fails
        else:
            error_msg = result.get("error", "Unknown error") if result else "Processing returned no result"
            logger.error(f"Case processing failed for {case_id}: {error_msg}")
            try:
                db.rollback()
            except Exception:
                pass
            upload_agent_service.update_processing_status(db, session_id, "error", 0)
            
            # Ensure case status is set to FAILED
            try:
                case = db.query(Case).filter(Case.id == case_id).first()
                if case:
                    case.status = CaseStatus.FAILED
                    db.commit()
                    logger.info(f"Set case {case_id} status to FAILED")
            except Exception as db_error:
                logger.error(f"Failed to update case status: {db_error}", exc_info=True)
                db.rollback()
        
    except Exception as e:
        logger.error(f"Error processing case {case_id}: {e}", exc_info=True)
        # Rollback first so the session is usable for error-handling updates (avoids PendingRollbackError)
        try:
            db.rollback()
        except Exception:
            pass
        try:
            upload_agent_service.update_processing_status(db, session_id, "error", 0)
            
            # Ensure case status is set to FAILED
            case = db.query(Case).filter(Case.id == case_id).first()
            if case:
                case.status = CaseStatus.FAILED
                db.commit()
                logger.info(f"Set case {case_id} status to FAILED due to exception")
        except Exception as eh:
            logger.error(f"Error during case failure cleanup: {eh}", exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            
    finally:
        db.close()


@router.get("/status/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str, db: Session = Depends(get_db)):
    """Get current session status. When case is processed by UM-Jobs, derive complete from Case.status."""
    session = upload_agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    processing_status = session.processing_status
    processing_progress = session.processing_progress
    # UM-Jobs updates Case.status to READY when done but does not update the session.
    # Derive "complete" from Case so the UI gets acknowledgement on the next poll.
    if session.case_id and processing_status != "complete":
        case_row = db.query(Case).filter(Case.id == session.case_id).first()
        if case_row and case_row.status == CaseStatus.READY:
            processing_status = "complete"
            processing_progress = 100
            upload_agent_service.update_processing_status(db, session_id, "complete", 100, session.case_id)

    return SessionStatusResponse(
        session_id=session_id,
        state=ConversationStateEnum(session.state),
        patient_info=PatientInfoResponse(**(session.patient_info if isinstance(session.patient_info, dict) else session.patient_info.to_dict())),
        case_number=session.case_number,
        priority=session.priority,
        files=session.files,
        processing_status=processing_status,
        processing_progress=processing_progress,
        case_id=session.case_id
    )


@router.get("/messages/{session_id}")
async def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    """Get all messages in a session"""
    session = upload_agent_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "messages": session.messages
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a session"""
    success = upload_agent_service.delete_session(db, session_id)
    
    # Also clean up temp files
    try:
        import shutil
        temp_dir = storage_service.get_case_directory(f"temp_{session_id}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    except Exception as e:
        logger.warning(f"Failed to clean temp directory: {e}")
    
    if success:
        return {"message": "Session deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

