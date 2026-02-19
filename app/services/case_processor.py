"""Case processing orchestration service with RAG support"""

import uuid
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.models.case import Case, CaseStatus
from app.models.case_file import CaseFile
from app.models.extraction import ClinicalExtraction
from app.models.document_chunk import DocumentChunk
from app.services.storage_service import storage_service
from app.services.pdf_service import pdf_service
from app.services.llm_service import llm_service
from app.services.timeline_service import timeline_service
from app.services.contradiction_service import contradiction_service
from app.services.summary_service import summary_service
from app.services.chunking_service import chunking_service, ChunkData
from app.services.embedding_service import embedding_service
from app.services.pgvector_service import pgvector_service  # Added
from app.services.clinical_agent import clinical_agent
from app.services.pdf_analyzer_service import pdf_analyzer_service
from app.repositories.chunk_repository import chunk_repository
from app.db.session import SessionLocal
from app.core.config import settings

logger = logging.getLogger(__name__)


class CaseProcessor:
    """Orchestrates the full case processing orchestration service with RAG support"""

    def __init__(self):
        self.use_rag = True

    # ... (rest of class)

    def _process_chunks(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        case_files: List[CaseFile],
        file_page_mapping: Dict[str, Dict[int, str]],
        file_page_bbox_mapping: Optional[Dict[str, Dict[int, List[Dict]]]] = None
    ) -> Dict[str, DocumentChunk]:
        """
        Process documents into chunks and store in PGVector
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID for scoping
            case_files: List of case files
            file_page_mapping: Mapping of file_id -> {page_num -> text}
            file_page_bbox_mapping: Mapping of file_id -> {page_num -> text_segments with bbox}
            
        Returns:
            Dict mapping vector_id to DocumentChunk
        """
        all_chunks: List[ChunkData] = []
        chunk_mapping: Dict[str, DocumentChunk] = {}
        
        # Chunk each file
        for case_file in case_files:
            if case_file.id not in file_page_mapping:
                continue
            
            # Use bbox-aware chunking if bbox data is available
            if file_page_bbox_mapping and case_file.id in file_page_bbox_mapping:
                bbox_mapping = file_page_bbox_mapping[case_file.id]
                file_chunks = []
                chunk_index = 0
                
                for page_number in sorted(file_page_mapping[case_file.id].keys()):
                    page_text = file_page_mapping[case_file.id][page_number]
                    text_segments = bbox_mapping.get(page_number, [])
                    
                    page_chunks = chunking_service.chunk_page_with_bbox(
                        text=page_text,
                        text_segments=text_segments,
                        page_number=page_number,
                        file_id=case_file.id,
                        case_id=case_id,
                        start_chunk_index=chunk_index
                    )
                    file_chunks.extend(page_chunks)
                    chunk_index += len(page_chunks)
            else:
                # Fallback to regular chunking if no bbox data
                file_chunks = chunking_service.chunk_document(
                    file_page_mapping=file_page_mapping[case_file.id],
                    file_id=case_file.id,
                    case_id=case_id
                )
            
            all_chunks.extend(file_chunks)
        
        if not all_chunks:
            logger.warning(f"No chunks created for case {case_id}")
            return {}
        
        logger.info(f"Created {len(all_chunks)} chunks for case {case_id}")
        
        # Generate embeddings in batches
        import time
        embedding_start = time.time()
        chunk_texts = [c.chunk_text for c in all_chunks]
        logger.info(f"[TIMING] Starting embedding generation for {len(chunk_texts)} chunks for case {case_id}")
        embeddings = embedding_service.generate_embeddings_batch(chunk_texts)
        embedding_time = time.time() - embedding_start
        logger.info(f"[TIMING] Embedding generation completed in {embedding_time:.2f}s for case {case_id}")
        
        # Prepare chunks for Database
        db_chunks = []
        
        for i, chunk_data in enumerate(all_chunks):
            # Create database chunk WITH EMBEDDING
            db_chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                case_id=case_id,
                user_id=user_id,
                file_id=chunk_data.file_id,
                chunk_index=chunk_data.chunk_index,
                page_number=chunk_data.page_number,
                section_type=chunk_data.section_type,
                chunk_text=chunk_data.chunk_text,
                char_start=chunk_data.char_start,
                char_end=chunk_data.char_end,
                token_count=chunk_data.token_count,
                vector_id=chunk_data.vector_id,
                bbox=chunk_data.bbox,
                created_at=datetime.utcnow(),
                embedding=embeddings[i]  # STORE VECTOR DIRECTLY
            )
            db_chunks.append(db_chunk)
            chunk_mapping[chunk_data.vector_id] = db_chunk
            
        # Save chunks to database in batches with retry (prevents SSL timeout on large docs)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                chunk_repository.bulk_create(db, db_chunks, batch_size=50)
                logger.info(f"Upserted {len(db_chunks)} chunks with embeddings to PGVector for case {case_id}")
                break  # Success
            except OperationalError as e:
                error_msg = str(e).lower()
                is_connection_error = ("ssl" in error_msg or "connection" in error_msg or "closed" in error_msg)
                
                if is_connection_error and attempt < max_retries - 1:
                    logger.warning(f"Connection error inserting chunks (attempt {attempt + 1}/{max_retries}), retrying in 2s: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"Failed to insert chunks after {attempt + 1} attempts: {e}")
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    raise
        
        return chunk_mapping

    async def process_case(self, case_id: str, use_rag: Optional[bool] = None, request_metadata: Optional[Dict] = None) -> Dict:
        """
        Process a case through the full pipeline

        Args:
            case_id: Case ID to process
            use_rag: Override RAG usage (default: based on config)
            request_metadata: Optional request metadata (request_type, requested_service, request_date, urgency)

        Returns:
            Processing result dictionary
        """
        # Create new database session for background task
        db = SessionLocal()
        should_use_rag = use_rag if use_rag is not None else self.use_rag
        
        logger.info(f"Starting case processing for {case_id}, RAG enabled: {should_use_rag}")
        
        try:
            # Get case from database
            case = db.query(Case).filter(Case.id == case_id).first()
            if not case:
                logger.error(f"Case {case_id} not found in database")
                return {"success": False, "error": "Case not found"}
            
            user_id = case.user_id
            logger.info(f"Found case {case_id} with status {case.status} for user {user_id}")

            try:
                # Step 1: Get all files for the case (before status update)
                case_files = db.query(CaseFile).filter(
                    CaseFile.case_id == case_id
                ).order_by(CaseFile.file_order).all()
                
                if not case_files:
                    case.status = CaseStatus.FAILED
                    db.commit()
                    return {"success": False, "error": "No files found for case"}

                # Step 1.5: Check for non-medical documents (Safety Net) - only if guardrail is enabled
                if settings.ENABLE_MEDICAL_GUARDRAIL:
                    for cf in case_files:
                        if cf.document_type and cf.document_type.startswith("non_medical_"):
                            error_msg = f"Document '{cf.file_name}' identified as {cf.document_type.replace('non_medical_', '').title()}. " \
                                        f"Cannot process non-medical records."
                            logger.error(f"Safety Net Triggered: {error_msg} for case {case_id}")
                            case.status = CaseStatus.FAILED
                            db.commit()
                            return {
                                "success": False, 
                                "error": error_msg,
                                "case_id": case_id
                            }

                # If reprocessing, remove any existing extraction to avoid unique constraint on case_id
                existing_extraction = db.query(ClinicalExtraction).filter(
                    ClinicalExtraction.case_id == case_id
                ).first()
                if existing_extraction:
                    db.delete(existing_extraction)
                    db.flush()

                # Also delete existing chunks if reprocessing
                if should_use_rag:
                    self._delete_existing_chunks(db, case_id, user_id)

                # Update status to processing only after files are confirmed
                case.status = CaseStatus.PROCESSING
                db.commit()

                # Step 2: Extract text from all PDFs and track file/page mapping (parallelized)
                # Extract data from SQLAlchemy objects BEFORE passing to threads (thread-safety)
                file_data = []
                for case_file in case_files:
                    file_data.append({
                        "id": case_file.id,
                        "file_name": case_file.file_name,
                        "file_path": case_file.file_path
                    })
                
                all_extracted_text = []
                file_page_mapping = {}  # Maps file_id -> {page_num -> text}
                file_page_bbox_mapping = {}  # Maps file_id -> {page_num -> text_segments with bbox}
                combined_text_parts = []
                
                successful_extractions = 0
                failed_files = []
                
                def extract_pdf_file(file_info: dict) -> tuple:
                    """Extract text from a single PDF file with coordinates"""
                    try:
                        logger.info(f"Extracting text with coordinates from file: {file_info['file_name']} (path: {file_info['file_path']})")
                        # Use coordinate extraction for precise highlighting
                        pdf_result = pdf_service.extract_text_with_coordinates(file_info['file_path'])
                        if pdf_result.get("error"):
                            error_msg = pdf_result.get("error", "Unknown error")
                            logger.error(f"Error extracting text from file {file_info['file_name']}: {error_msg}")
                            return (file_info, None, file_info['file_name'])
                        return (file_info, pdf_result, None)
                    except Exception as e:
                        logger.error(f"Exception extracting text from file {file_info['file_name']}: {e}", exc_info=True)
                        return (file_info, None, file_info['file_name'])
                
                # Extract PDFs in parallel
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {
                        executor.submit(extract_pdf_file, file_info): file_info 
                        for file_info in file_data
                    }
                    
                    for future in as_completed(futures):
                        file_info, pdf_result, error_file = future.result()
                        
                        if error_file:
                            failed_files.append(error_file)
                            continue
                        
                        if pdf_result is None:
                            failed_files.append(file_info['file_name'])
                            continue
                    
                        # Store file/page mapping with text and bbox data
                        file_page_mapping[file_info['id']] = {}
                        file_page_bbox_mapping[file_info['id']] = {}
                        for page_data in pdf_result.get("pages", []):
                            page_num = page_data.get("page_number", 0)
                            page_text = page_data.get("text", "")
                            text_segments = page_data.get("text_segments", [])
                            file_page_mapping[file_info['id']][page_num] = page_text
                            file_page_bbox_mapping[file_info['id']][page_num] = text_segments
                            
                            # Add file context to text
                            combined_text_parts.append(
                                f"\n\n--- File: {file_info['file_name']} | Page {page_num} ---\n\n{page_text}"
                            )
                        
                        all_extracted_text.append(pdf_result["text"])
                        successful_extractions += 1
                
                # Require at least one successful extraction
                if successful_extractions == 0:
                    error_msg = f"Failed to extract text from all {len(case_files)} file(s)"
                    if failed_files:
                        error_msg += f". Failed files: {', '.join(failed_files)}"
                    logger.error(error_msg)
                    case.status = CaseStatus.FAILED
                    db.commit()
                    return {
                        "success": False,
                        "error": error_msg,
                        "case_id": case_id
                    }
                
                # Log warnings for partial failures
                if failed_files:
                    logger.warning(f"Successfully extracted {successful_extractions} of {len(case_files)} files. Failed: {', '.join(failed_files)}")

                # Combine all text for LLM processing
                extracted_text = "\n\n".join(all_extracted_text)
                combined_text_with_context = "".join(combined_text_parts)
                
                # Validate that we have extracted text
                if not extracted_text or not extracted_text.strip():
                    case.status = CaseStatus.FAILED
                    db.commit()
                    return {
                        "success": False,
                        "error": "No text could be extracted from any uploaded files",
                        "case_id": case_id
                    }
                
                # Extract patient demographics (DOB) from documents for PDF generation
                patient_dob = None
                try:
                    # Use first 5000 chars for quick DOB extraction
                    text_sample = extracted_text[:5000] if extracted_text else ""
                    if text_sample:
                        patient_info = pdf_analyzer_service._extract_patient_info_regex(text_sample)
                        if patient_info and patient_info.dob:
                            patient_dob = patient_info.dob
                            logger.info(f"Extracted DOB for case {case_id}: {patient_dob}")
                except Exception as e:
                    logger.warning(f"Failed to extract DOB for case {case_id}: {e}")
                    # Continue without DOB - not critical for processing
                
                # Update page count
                total_pages = sum(f.page_count for f in case_files)
                case.page_count = total_pages
                db.commit()

                # Step 3: Chunk documents and store in FAISS (if RAG enabled)
                chunk_mapping = {}  # Maps vector_id -> chunk for source linking
                if should_use_rag:
                    case.status = CaseStatus.PROCESSING
                    db.commit()
                    
                    chunk_mapping = self._process_chunks(
                        db=db,
                        case_id=case_id,
                        user_id=user_id,
                        case_files=case_files,
                        file_page_mapping=file_page_mapping,
                        file_page_bbox_mapping=file_page_bbox_mapping
                    )
                    logger.info(f"Created {len(chunk_mapping)} chunks for case {case_id}")

                # Step 4: Extract clinical information
                import time
                step_start = time.time()
                case.status = CaseStatus.EXTRACTING
                db.commit()

                if should_use_rag and chunk_mapping:
                    # Use RAG-enhanced clinical agent (async)
                    logger.info(f"[TIMING] Starting clinical extraction (RAG) for case {case_id}")
                    extraction_start = time.time()
                    extraction_result = await clinical_agent.extract_all(
                        db=db,
                        case_id=case_id,
                        user_id=user_id,
                        fallback_text=combined_text_with_context
                    )
                    extraction_time = time.time() - extraction_start
                    logger.info(f"[TIMING] Clinical extraction completed in {extraction_time:.2f}s for case {case_id}")
                    clinical_data = extraction_result.data
                    extraction_sources = extraction_result.sources
                    
                    # Flag low-confidence extractions
                    low_confidence_items = []
                    confidence_threshold = 0.5  # Configurable
                    
                    for data_type in ["medications", "labs", "diagnoses", "procedures", "vitals", "allergies", "imaging"]:
                        items = clinical_data.get(data_type, [])
                        for idx, item in enumerate(items):
                            if item.get('confidence_score', 1.0) < confidence_threshold:
                                low_confidence_items.append({
                                    'type': data_type,
                                    'index': idx,
                                    'item': item.get('name') or item.get('test_name') or item.get('allergen') or str(item),
                                    'confidence': item.get('confidence_score', 0.0)
                                })
                    
                    if low_confidence_items:
                        logger.warning(f"[VALIDATION] Case {case_id} has {len(low_confidence_items)} low-confidence items")
                        for lc_item in low_confidence_items[:10]:  # Log first 10
                            logger.warning(f"  - {lc_item['type']}: {lc_item['item']} (confidence: {lc_item['confidence']:.2f})")
                    
                    # CRITICAL: Merge sources into extracted_data items
                    merge_start = time.time()
                    clinical_data = self._merge_sources_into_data(
                        clinical_data=clinical_data,
                        extraction_sources=extraction_sources,
                        case_files=case_files
                    )
                    merge_time = time.time() - merge_start
                    logger.info(f"[TIMING] Source merging completed in {merge_time:.2f}s for case {case_id}")
                    
                    # NEW: Create entity sources (industry-standard source linking)
                    # Make this optional - if table doesn't exist, skip gracefully
                    try:
                        from app.services.entity_source_service import EntitySourceService
                        entity_source_service = EntitySourceService()
                        file_lookup = {f.id: f.file_name for f in case_files}
                        entity_source_start = time.time()
                        entity_count = entity_source_service.create_sources_from_extraction(
                            db=db,
                            case_id=case_id,
                            user_id=user_id,
                            extracted_data=clinical_data,
                            extraction_sources=extraction_sources,
                            file_lookup=file_lookup
                        )
                        entity_source_time = time.time() - entity_source_start
                        logger.info(f"[TIMING] Entity source creation completed in {entity_source_time:.2f}s for case {case_id} ({entity_count} sources created)")
                    except Exception as e:
                        error_msg = str(e)
                        # Always rollback so session is usable; re-raise connection/session errors so processing fails cleanly
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        if "entity_sources" in error_msg.lower() or "does not exist" in error_msg.lower():
                            logger.warning(f"[TIMING] Entity source creation skipped: table not found. Run migration: alembic upgrade head")
                        else:
                            logger.warning(f"[TIMING] Entity source creation failed: {error_msg}")
                            # Re-raise so case processing fails and caller can mark case as failed (avoids commit on broken session)
                            raise
                else:
                    # Fallback to direct LLM extraction (async)
                    logger.info(f"[TIMING] Starting direct LLM extraction for case {case_id}")
                    extraction_start = time.time()
                    clinical_data = await llm_service.extract_clinical_information(
                        extracted_text, 
                        file_page_mapping=file_page_mapping,
                        combined_text=combined_text_with_context
                    )
                    extraction_time = time.time() - extraction_start
                    logger.info(f"[TIMING] Direct LLM extraction completed in {extraction_time:.2f}s for case {case_id}")
                    extraction_sources = []

                step_time = time.time() - step_start
                logger.info(f"[TIMING] Step 4 (Extraction) total time: {step_time:.2f}s for case {case_id}")

                # Step 5: Build timeline
                step_start = time.time()
                case.status = CaseStatus.TIMELINE_BUILDING
                db.commit()

                # Build timeline (mostly CPU-bound, but RAG supplement is async)
                # Run in thread but handle async RAG internally
                logger.info(f"[TIMING] Starting timeline building for case {case_id}")
                timeline_result = await asyncio.to_thread(
                    timeline_service.build_timeline,
                    clinical_data, extracted_text, db, case_id, user_id
                )
                # timeline_result is now a Dict with 'summary' and 'detailed' keys
                timeline = timeline_result.get("detailed", [])
                timeline_summary = timeline_result.get("summary", [])
                
                # Categorize medications into admission_home, inpatient, discharge
                categorized_medications = await asyncio.to_thread(
                    timeline_service.categorize_medications,
                    clinical_data.get("medications", []),
                    timeline
                )
                
                # Add categorized medications to extracted data
                clinical_data["medications_categorized"] = categorized_medications
                
                # Also add category field to each individual medication
                for category, meds in categorized_medications.items():
                    for categorized_med in meds:
                        med_name = categorized_med.get("name", "").lower().strip()
                        for orig_med in clinical_data.get("medications", []):
                            orig_name = orig_med.get("name", "").lower().strip()
                            if orig_name == med_name:
                                orig_med["category"] = categorized_med.get("category")
                                orig_med["category_date"] = categorized_med.get("category_date")
                                break
                
                # Compute vitals per-day ranges
                vitals_per_day_ranges = await asyncio.to_thread(
                    timeline_service.compute_vitals_per_day_ranges,
                    clinical_data.get("vitals", []),
                    timeline
                )
                
                # Add vitals per-day ranges to extracted data
                clinical_data["vitals_per_day_ranges"] = vitals_per_day_ranges
                
                step_time = time.time() - step_start
                logger.info(f"[TIMING] Step 5 (Timeline) completed in {step_time:.2f}s for case {case_id}")
                logger.info(f"[TIMING] Timeline built with {len(timeline)} detailed events and {len(timeline_summary)} summary events for case {case_id}")
                logger.info(f"[TIMING] Medications categorized: {len(categorized_medications.get('admission_home', []))} admission/home, {len(categorized_medications.get('inpatient', []))} inpatient, {len(categorized_medications.get('discharge', []))} discharge")
                logger.info(f"[TIMING] Vitals per-day ranges computed for {len(vitals_per_day_ranges)} hospital days")
                if len(timeline) > 0:
                    logger.debug(f"[TIMING] First timeline event: {timeline[0].get('event_type', 'unknown')} on {timeline[0].get('date', 'unknown date')}")
                
                # NEW: Create entity sources for timeline events
                # Make this optional - if table doesn't exist, skip gracefully
                # Use a savepoint to isolate entity source creation from main transaction
                timeline_source_count = 0
                try:
                    from app.services.entity_source_service import EntitySourceService
                    entity_source_service = EntitySourceService()
                    timeline_source_start = time.time()
                    
                    # Create a savepoint to isolate entity source creation
                    savepoint = db.begin_nested()
                    try:
                        # Collect all timeline sources for bulk creation
                        timeline_source_data = []
                        
                        for event in timeline:
                            if isinstance(event, dict) and event.get("id"):
                                # Get source information from event
                                source_file = event.get("source_file")
                                source_page = event.get("source_page") or event.get("page_number")
                                details = event.get("details", {})
                                
                                # Try to get from details if not in event
                                if not source_file:
                                    source_file = details.get("source_file") if isinstance(details, dict) else None
                                if not source_page:
                                    source_page = details.get("source_page") if isinstance(details, dict) else None
                                
                                # Find file_id from source_file
                                file_id = None
                                if source_file:
                                    for case_file in case_files:
                                        if case_file.file_name == source_file:
                                            file_id = case_file.id
                                            break
                                
                                # Prepare source data if we have location data
                                if file_id and source_page:
                                    # Get chunk_id if available from extraction_sources
                                    chunk_id = None
                                    source_type = event.get("source", "")
                                    if source_type and extraction_sources:
                                        # Find matching source by type
                                        for source in extraction_sources:
                                            if source.get("type") == source_type:
                                                chunk_id = source.get("chunk_id")
                                                break
                                    
                                    # Handle page number type conversion
                                    try:
                                        page_val = int(source_page) if isinstance(source_page, (int, str)) and str(source_page).isdigit() else None
                                    except (ValueError, TypeError):
                                        page_val = None
                                    
                                    if page_val is not None:
                                        timeline_source_data.append({
                                            "entity_type": "timeline",
                                            "entity_id": f"timeline:{event['id']}",
                                            "chunk_id": chunk_id,
                                            "file_id": file_id,
                                            "page_number": page_val,
                                            "snippet": event.get("description", "")[:500]
                                        })
                        
                        # Bulk create using optimized service
                        if timeline_source_data:
                            timeline_source_count = entity_source_service.bulk_create_entity_sources(
                                db=db,
                                sources_data=timeline_source_data,
                                case_id=case_id,
                                user_id=user_id,
                                commit=False  # Do not commit here, let savepoint handle it
                            )
                        
                        savepoint.commit()
                        
                    except Exception as e:
                        # Rollback only the savepoint, not the main transaction
                        savepoint.rollback()
                        raise
                    
                    timeline_source_time = time.time() - timeline_source_start
                    logger.info(f"[TIMING] Timeline entity source creation completed in {timeline_source_time:.2f}s for case {case_id} ({timeline_source_count} sources created)")
                except Exception as e:
                    # If entity_sources table doesn't exist or other error, log and continue
                    # DO NOT rollback main transaction - timeline is already built and should be saved
                    error_msg = str(e)
                    if "entity_sources" in error_msg.lower() or "does not exist" in error_msg.lower():
                        logger.warning(f"[TIMING] Timeline entity source creation skipped: table not found. Run migration: alembic upgrade head. Error: {error_msg}")
                    else:
                        logger.warning(f"[TIMING] Timeline entity source creation failed (non-critical): {error_msg}")
                    # Do NOT rollback - entity source creation is optional

                # Step 6: Detect contradictions (with file/page mapping) - CPU-bound, run in thread
                step_start = time.time()
                logger.info(f"[TIMING] Starting contradiction detection for case {case_id}")
                contradictions = await asyncio.to_thread(
                    contradiction_service.detect_contradictions,
                    clinical_data, timeline, file_page_mapping
                )
                step_time = time.time() - step_start
                logger.info(f"[TIMING] Step 6 (Contradictions) completed in {step_time:.2f}s for case {case_id}")

                # Step 7: Generate comprehensive summary (async)
                step_start = time.time()
                logger.info(f"[TIMING] Starting comprehensive summary generation for case {case_id}")
                
                # Collect all chunk texts for Tier 2 (will be de-identified before sending to Claude)
                all_chunk_texts = [chunk.chunk_text for chunk in chunk_mapping.values()] if chunk_mapping else []
                logger.info(f"[TIMING] Passing {len(all_chunk_texts)} document chunks to summary service for case {case_id}")
                
                summary = await summary_service.generate_summary(
                    clinical_data,
                    timeline,
                    contradictions,
                    case.patient_name,
                    case.case_number,
                    db=db,
                    case_id=case_id,
                    user_id=user_id,
                    document_chunks=all_chunk_texts
                )
                step_time = time.time() - step_start
                logger.info(f"[TIMING] Step 7 (Comprehensive Summary) completed in {step_time:.2f}s for case {case_id}")

                # Step 7.5: Generate executive summary (async)
                step_start = time.time()
                logger.info(f"[TIMING] Starting executive summary generation for case {case_id}")
                executive_summary = await summary_service.generate_executive_summary(
                    clinical_data,
                    timeline,
                    contradictions,
                    case.patient_name,
                    case.case_number,
                    db=db,
                    case_id=case_id,
                    user_id=user_id,
                    document_chunks=all_chunk_texts
                )
                step_time = time.time() - step_start
                logger.info(f"[TIMING] Step 7.5 (Executive Summary) completed in {step_time:.2f}s for case {case_id}")

                # Step 8: Prepare source mapping for storage
                source_mapping = {
                    "file_page_mapping": file_page_mapping,
                    "files": [
                        {
                            "id": f.id,
                            "file_name": f.file_name,
                            "page_count": f.page_count
                        }
                        for f in case_files
                    ],
                    "rag_enabled": should_use_rag,
                    "chunk_count": len(chunk_mapping),
                    "extraction_sources": extraction_sources
                }

                # Step 9: Add patient demographics (DOB) to extracted_data for PDF generation
                if patient_dob:
                    if not isinstance(clinical_data, dict):
                        clinical_data = {}
                    if 'patient_demographics' not in clinical_data:
                        clinical_data['patient_demographics'] = {}
                    clinical_data['patient_demographics']['dob'] = patient_dob
                
                # Step 9.5: Add request metadata if provided
                if request_metadata:
                    if not isinstance(clinical_data, dict):
                        clinical_data = {}
                    clinical_data['request_metadata'] = request_metadata
                
                # Step 10: Save extraction results
                logger.info(f"[TIMING] Saving extraction with {len(timeline)} detailed timeline events and {len(timeline_summary)} summary events for case {case_id}")
                extraction = ClinicalExtraction(
                    id=str(uuid.uuid4()),
                    case_id=case_id,
                    user_id=user_id,
                    extracted_data=clinical_data,
                    timeline=timeline,  # Detailed timeline with all events
                    timeline_summary=timeline_summary,  # Summary timeline with major events only
                    contradictions=contradictions,
                    summary=summary,
                    executive_summary=executive_summary,  # Concise 5-10 bullet summary for PDFs
                    source_mapping=source_mapping,
                    created_at=datetime.utcnow()
                )

                db.add(extraction)

                # Update case status
                case.status = CaseStatus.READY
                case.processed_at = datetime.utcnow()
                db.commit()

                return {
                    "success": True,
                    "case_id": case_id,
                    "status": "ready",
                    "message": "Case processed successfully",
                    "rag_enabled": should_use_rag,
                    "chunks_created": len(chunk_mapping)
                }

            except Exception as e:
                db.rollback()
                logger.error(f"Error processing case {case_id}: {e}", exc_info=True)
                try:
                    case.status = CaseStatus.FAILED
                    db.commit()
                except:
                    db.rollback()
                return {
                    "success": False,
                    "error": str(e),
                    "case_id": case_id
                }
        finally:
            db.close()

    def _merge_sources_into_data(
        self,
        clinical_data: Dict,
        extraction_sources: List[Dict],
        case_files: List
    ) -> Dict:
        """
        Merge source information from extraction_sources into clinical_data items.
        
        This ensures that each extracted item (medication, lab, etc.) has
        source_file and source_page fields for proper source linking.
        
        Improved matching with validation and handling of mismatched counts.
        
        Args:
            clinical_data: Extracted clinical data
            extraction_sources: List of source references from RAG
            case_files: List of CaseFile objects for file_id to file_name mapping
            
        Returns:
            Clinical data with sources merged into items
        """
        # Create file_id to file_name lookup
        file_lookup = {f.id: f.file_name for f in case_files}
        
        # Group sources by type with validation
        sources_by_type = {}
        for source in extraction_sources:
            source_type = source.get("type", "")
            if source_type:
                if source_type not in sources_by_type:
                    sources_by_type[source_type] = []
                sources_by_type[source_type].append(source)
        
        # Merge sources into each data type
        data_types = {
            "medication": "medications",
            "lab": "labs",
            "diagnosis": "diagnoses",
            "procedure": "procedures",
            "vital": "vitals",
            "allergy": "allergies",
            "imaging": "imaging",
            "social_factors": "social_factors",  # Social factors (housing, caregiver, cognition, placement barriers)
            "therapy_notes": "therapy_notes",  # PT/OT/Speech therapy notes with functional status
            "functional_status": "functional_status"  # Functional status assessments
        }
        
        for source_type, data_key in data_types.items():
            items = clinical_data.get(data_key, [])
            sources = sources_by_type.get(source_type, [])
            
            # Validate and log mismatches
            if not items:
                if sources:
                    logger.debug(f"No {data_key} items found but {len(sources)} sources available for type {source_type}")
                continue
            
            if not sources:
                logger.debug(f"No sources found for {data_key} items (type {source_type})")
                # Continue without sources - items will not have source_file/source_page
                continue
            
            # Log count mismatches (expected when RAG finds multiple chunks per item)
            if len(items) != len(sources):
                logger.debug(
                    f"Source count mismatch for {data_key}: {len(items)} items but {len(sources)} sources. "
                    f"Type: {source_type} (This is expected when items are mentioned in multiple documents/pages)"
                )
            
            # Match sources to items with improved logic
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                
                # Use inlined source if available (highest priority, matched by ClinicalAgent)
                if item.get("source_page") and (item.get("source_file_id") or item.get("source_file")):
                    file_id = item.get("source_file_id")
                    if file_id and file_id in file_lookup:
                        item["source_file"] = file_lookup[file_id]
                    continue

                # Determine which source to use from extraction_sources list ONLY if no inline source
                source = None
                if len(sources) == len(items):
                    source = sources[idx]
                elif len(sources) > 0:
                    # Attempt to find a source that contains the item name (late matching)
                    name = item.get("name") or item.get("test_name") or ""
                    if name:
                        for s in sources:
                            # snippet if available
                            snippet = s.get("snippet", "").lower()
                            if snippet and name.lower() in snippet:
                                source = s
                                break
                    # Fallback to index-based only as the absolute last resort
                    if not source:
                        source_idx = idx % len(sources)
                        source = sources[source_idx]
                
                if source:
                    file_id = source.get("file_id")
                    page_number = source.get("page_number")
                    
                    # Validate source type matches (sanity check)
                    source_type_check = source.get("type", "")
                    if source_type_check and source_type_check != source_type:
                        logger.warning(
                            f"Source type mismatch: expected {source_type}, got {source_type_check} "
                            f"for {data_key} item at index {idx}"
                        )
                    
                    # Add source_file, source_page, and bbox to item
                    if file_id and file_id in file_lookup:
                        item["source_file"] = file_lookup[file_id]
                        item["source_page"] = page_number
                        if source.get("bbox"):
                            item["bbox"] = source.get("bbox")
                    elif file_id:
                        # File ID exists but not in lookup (shouldn't happen, but handle gracefully)
                        logger.warning(
                            f"File ID {file_id} not found in file_lookup for {data_key} item at index {idx}"
                        )
                        if page_number:
                            item["source_page"] = page_number
                    elif page_number:
                        # If we have page but no file_id, use page only
                        item["source_page"] = page_number
                        logger.debug(
                            f"Added source_page only (no file_id) for {data_key} item at index {idx}"
                        )
                else:
                    # No source available for this item
                    logger.debug(f"No source available for {data_key} item at index {idx}")
        
        return clinical_data

    def _delete_existing_chunks(self, db: Session, case_id: str, user_id: str) -> None:
        """Delete existing chunks for a case (for reprocessing)"""
        # Delete from database (and vector store via pgvector)
        chunk_repository.delete_by_case_id(db, case_id)
        logger.info(f"Deleted existing chunks for case {case_id} (user {user_id})")


# Singleton instance
case_processor = CaseProcessor()
