"""Source document API endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
import os
import logging
from sqlalchemy.orm import Session
import tempfile

from app.db.session import get_db

logger = logging.getLogger(__name__)
from app.db.dependencies import (
    get_case_repository,
    get_case_file_repository,
    get_extraction_repository,
    get_source_link_repository,
)
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.source_link_repository import SourceLinkRepository
from app.services.pdf_service import pdf_service
from app.services.source_link_service import build_source_link_service
from app.core.config import settings
from app.services.entity_source_service import EntitySourceService
from app.repositories.entity_source_repository import EntitySourceRepository
from app.services.source_validation_service import source_validation_service

router = APIRouter()


def get_entity_source_repository() -> EntitySourceRepository:
    """Dependency for EntitySourceRepository"""
    return EntitySourceRepository()


def get_entity_source_service() -> EntitySourceService:
    """Dependency for EntitySourceService"""
    return EntitySourceService()


@router.get("/contradiction-evidence/{case_id}/{contradiction_id}")
async def get_contradiction_sources(
    case_id: str,
    contradiction_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
):
    """Get sources for a contradiction"""
    logger.info(f"Fetching contradiction sources for case_id={case_id}, contradiction_id={contradiction_id}")
    
    case = case_repository.get_by_id(db, case_id)
    if not case:
        print(f"[DEBUG] -> Case not found: {case_id}")
        raise HTTPException(status_code=404, detail="Case not found")

    extraction = extraction_repository.get_by_case_id(db, case_id)

    if not extraction:
        print(f"[DEBUG] -> Extraction not found for case: {case_id}")
        raise HTTPException(status_code=404, detail="Extraction not found")
        
    if not extraction.contradictions:
        print(f"[DEBUG] -> No contradictions in extraction for case: {case_id}")
        raise HTTPException(status_code=404, detail="Contradictions not found")

    if not isinstance(extraction.contradictions, list):
        print(f"[DEBUG] -> Contradictions is not a list: {type(extraction.contradictions)}")
        raise HTTPException(status_code=404, detail="Contradictions format error")

    # Find the contradiction
    contradiction = None
    for c in extraction.contradictions:
        if isinstance(c, dict) and c.get("id") == contradiction_id:
            contradiction = c
            break

    if not contradiction:
        logger.warning(f"Contradiction ID {contradiction_id} not found in extraction. Available IDs: {[c.get('id') for c in extraction.contradictions if isinstance(c, dict)]}")
        raise HTTPException(status_code=404, detail="Contradiction not found")

    # Get source information
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
                # Find file_id from file name
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
                        # Try both int and string key for page number
                        page_text = page_mapping.get(source_page) or page_mapping.get(str(source_page), "")
                        sources.append(
                            {
                                "file_name": source_file,
                                "file_id": file_id,
                                "page": source_page,
                                "snippet": page_text[:500] if page_text else "",
                                "full_text": page_text,
                                "bbox": source.get("bbox"),
                                "term": source.get("term"),
                            }
                        )

    return {"contradiction": contradiction, "sources": sources}


@router.get("/cases/{case_id}/sources/timeline/{event_id}")
async def get_timeline_source(
    case_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
    entity_source_service: EntitySourceService = Depends(get_entity_source_service),
):
    """
    Get source for specific timeline event.

    This endpoint is maintained for backward compatibility but now uses
    the industry-standard EntitySourceService. New code should use
    /sources/{entity_type}/{entity_id} instead.

    Args:
        case_id: Case ID
        event_id: Timeline event ID

    Returns:
        Source information with file_id, page_number, bbox, snippet, etc.
    """
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Normalize event_id - remove type prefix if present (e.g., "timeline:abc" -> "abc")
    import urllib.parse

    event_id = urllib.parse.unquote(event_id)
    if event_id.startswith("timeline:"):
        event_id = event_id.replace("timeline:", "", 1)

    # Try EntitySource first (preferred)
    entity_id = f"timeline:{event_id}"
    entity_source = entity_source_service.get_entity_source(
        db=db,
        case_id=case_id,
        entity_type="timeline",
        entity_id=entity_id,
        user_id=case.user_id,
    )

    source_info = None
    item = {}

    if entity_source:
        # Get file name
        file_name = None
        if entity_source.file_id:
            case_file_repo = CaseFileRepository()
            case_file = case_file_repo.get_by_id(db, entity_source.file_id)
            if case_file:
                file_name = case_file.file_name

        # Get event description for highlight term
        description = source_validation_service.get_timeline_event_description(
            db, case_id, event_id
        )
        highlight_term = source_validation_service.extract_highlight_term(
            description=description, snippet=entity_source.snippet
        )

        # Load chunk data if chunk_id exists
        chunk_data = None
        correct_chunk = None
        correct_page = entity_source.page_number or 1

        from app.repositories.chunk_repository import ChunkRepository

        chunk_repo = ChunkRepository()

        if entity_source.chunk_id:
            try:
                chunk = chunk_repo.get_by_id(db, entity_source.chunk_id)
                if chunk:
                    # Validate that chunk contains the entity text
                    entity_term_clean = (highlight_term or "").strip().lower()
                    chunk_text_lower = (chunk.chunk_text or "").lower()

                    if entity_term_clean and entity_term_clean in chunk_text_lower:
                        correct_chunk = chunk
                        correct_page = chunk.page_number
            except Exception as e:
                logger.warning(f"Failed to load chunk: {e}", exc_info=True)

        # If linked chunk is missing or misaligned, search for correct chunk
        if not correct_chunk and entity_source.file_id:
            try:
                all_chunks = chunk_repo.get_by_file_id(db, entity_source.file_id)
                entity_term_clean = (highlight_term or "").strip().lower()

                if entity_term_clean and all_chunks:
                    import re
                    # Normalize for fuzzy matching: remove non-alphanumeric and extra whitespace
                    def normalize_text(text):
                        return re.sub(r'[^a-zA-Z0-9]', '', text.lower())
                    
                    norm_entity_term = normalize_text(entity_term_clean)
                    
                    best_match = None
                    best_match_score = 0

                    for chunk in all_chunks:
                        if not chunk.chunk_text:
                            continue
                        chunk_text_lower = chunk.chunk_text.lower()
                        
                        # 1. Exact match (preferred)
                        if entity_term_clean in chunk_text_lower:
                            score = 100 + len(entity_term_clean)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue
                                
                        # 2. Fuzzy match (normalized)
                        norm_chunk_text = normalize_text(chunk_text_lower)
                        if norm_entity_term in norm_chunk_text:
                            score = 50 + len(norm_entity_term)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue

                        # 3. Word overlap match (for tables/spaced text)
                        words = entity_term_clean.split()
                        if len(words) > 1:
                            match_count = sum(1 for word in words if word in chunk_text_lower and len(word) > 2)
                            if match_count >= len(words) * 0.7:  # 70% of words match
                                score = match_count * 10
                                if score > best_match_score:
                                    best_match_score = score
                                    best_match = chunk
                    
                    if best_match:
                        correct_chunk = best_match
                        correct_page = best_match.page_number
            except Exception as e:
                logger.warning(
                    f"Failed to search for correct chunk: {e}", exc_info=True
                )

        if correct_chunk:
            chunk_data = {
                "chunk_id": correct_chunk.id,
                "chunk_text": correct_chunk.chunk_text,
                "char_start": correct_chunk.char_start,
                "char_end": correct_chunk.char_end,
                "section_type": str(correct_chunk.section_type),
                "bbox": correct_chunk.bbox,  # Ensure bbox is in chunk data
            }
            
            # Propagate bbox to entity_source if missing
            if not getattr(entity_source, "bbox", None) and getattr(correct_chunk, "bbox", None):
                logger.info(
                    f"[EVIDENCE] Using bbox from found chunk: {correct_chunk.id}"
                )
                entity_source.bbox = correct_chunk.bbox

        source_info = {
            "file_id": entity_source.file_id,
            "file_name": file_name,
            "page": correct_page,
            "bbox": entity_source.bbox,
            "snippet": entity_source.snippet,
            "full_text": entity_source.full_text,
            "term": highlight_term if highlight_term else None,
            "chunk": chunk_data,
        }

        # Track evidence click for analytics
        try:
            from app.services.analytics_service import AnalyticsService

            analytics_service = AnalyticsService()
            source_type = "chunk" if entity_source.chunk_id else "file"
            analytics_service.track_evidence_click(
                db=db,
                user_id=case.user_id,
                case_id=case_id,
                entity_type="timeline",
                entity_id=event_id,
                source_type=source_type,
                file_id=entity_source.file_id,
                page_number=entity_source.page_number,
                chunk_id=entity_source.chunk_id,
            )
        except Exception as e:
            logger.warning(f"Failed to track evidence click: {e}", exc_info=True)

    else:
        # Fallback path: extraction.timeline
        extraction = extraction_repository.get_by_case_id(db, case_id)
        if not extraction or not extraction.timeline:
            raise HTTPException(
                status_code=404,
                detail=f"Source not found for timeline event {event_id} in case {case_id}",
            )

        # Handle different timeline formats (list vs dict)
        timeline_data = extraction.timeline
        timeline_events = []
        if isinstance(timeline_data, list):
            timeline_events = timeline_data
        elif isinstance(timeline_data, dict):
            # Try 'detailed' first, then 'summary'
            timeline_events = timeline_data.get("detailed", []) + timeline_data.get("summary", [])
        
        # If still empty, try extracted_data
        if not timeline_events and extraction.extracted_data:
            timeline_data = extraction.extracted_data.get("timeline")
            if isinstance(timeline_data, list):
                timeline_events = timeline_data
            elif isinstance(timeline_data, dict):
                timeline_events = timeline_data.get("detailed", []) + timeline_data.get("summary", [])

        event = next(
            (
                e
                for e in timeline_events
                if isinstance(e, dict) and (
                    str(e.get("id")) == str(event_id) or 
                    str(e.get("id")) == f"timeline:{event_id}" or
                    str(e.get("id")).endswith(str(event_id))
                )
            ),
            None,
        )

        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"Event {event_id} not found in extraction for case {case_id}",
            )

        item = event
        source_file = event.get("source_file")
        source_page = event.get("source_page") or event.get("page_number")

        if source_file and source_page:
            page_num = int(source_page) if str(source_page).isdigit() else 1
            source_mapping = extraction.source_mapping or {}
            files_list = source_mapping.get("files", [])
            file_id = None
            if isinstance(files_list, list):
                for file_info in files_list:
                    if (
                        isinstance(file_info, dict)
                        and file_info.get("file_name") == source_file
                    ):
                        file_id = file_info.get("id")
                        break

            file_page_mapping = source_mapping.get("file_page_mapping", {})
            page_text = ""
            if (
                file_id
                and isinstance(file_page_mapping, dict)
                and file_id in file_page_mapping
            ):
                page_mapping = file_page_mapping[file_id]
                if isinstance(page_mapping, dict):
                    page_text = page_mapping.get(page_num, "") or page_mapping.get(
                        str(page_num), ""
                    )

            source_info = {
                "file_id": file_id,
                "file_name": source_file,
                "page": page_num,
                "snippet": (
                    page_text[:500]
                    if page_text
                    else (event.get("description", "")[:500])
                ),
                "full_text": page_text,
                "term": source_validation_service.extract_highlight_term(
                    description=event.get("description"),
                    snippet=page_text,
                    entity_type="timeline",
                ),
                "chunk": None,
            }

    if not source_info:
        raise HTTPException(
            status_code=404,
            detail=f"Source details not available for timeline event {event_id}",
        )

    return {"item": item or {}, "source": source_info}


@router.get("/cases/{case_id}/sources/{data_type}/{data_id}")
async def get_source(
    case_id: str,
    data_type: str,
    data_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
    entity_source_service: EntitySourceService = Depends(get_entity_source_service),
):
    """
    Get source for specific extracted item.

    This endpoint is maintained for backward compatibility but now uses
    the industry-standard EntitySourceService with fallback to extraction.
    New code should use /sources/{entity_type}/{entity_id} instead.

    Args:
        case_id: Case ID
        data_type: Type of data ('medication', 'lab', 'diagnosis')
        data_id: Data identifier (index or ID, may include type prefix like "diagnosis:0")

    Returns:
        Source information with file_id, page_number, bbox, snippet, etc.
    """
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Normalize data_id - remove type prefix if present (e.g., "diagnosis:0" -> "0")
    import urllib.parse

    data_id = urllib.parse.unquote(data_id)
    if ":" in data_id:
        parts = data_id.split(":", 1)
        if parts[0] == data_type:
            data_id = parts[1]  # Remove type prefix

    # Build entity ID
    entity_id = f"{data_type}:{data_id}"

    # Try EntitySource first (preferred)
    entity_source = entity_source_service.get_entity_source(
        db=db,
        case_id=case_id,
        entity_type=data_type,
        entity_id=entity_id,
        user_id=case.user_id,
    )

    if entity_source:
        file_name = None
        if entity_source.file_id:
            case_file_repo = CaseFileRepository()
            case_file = case_file_repo.get_by_id(db, entity_source.file_id)
            if case_file:
                file_name = case_file.file_name

        highlight_term = source_validation_service.extract_highlight_term(
            snippet=entity_source.snippet,
            entity_type=data_type,
        )
        lab_item = None
        lab_matching_chunk_ids = []
        if data_type == "lab":
            try:
                extraction_for_lab = extraction_repository.get_by_case_id(db, case_id)
                labs_for_case = (
                    (extraction_for_lab.extracted_data or {}).get("labs", [])
                    if extraction_for_lab and isinstance(extraction_for_lab.extracted_data, dict)
                    else []
                )
                lab_index = int(data_id) if str(data_id).isdigit() else None
                if lab_index is not None and 0 <= lab_index < len(labs_for_case):
                    candidate = labs_for_case[lab_index]
                    if isinstance(candidate, dict):
                        lab_item = candidate
                        test_name = str(candidate.get("test_name") or "").strip()
                        value = str(candidate.get("value") or "").strip()
                        date = str(candidate.get("date") or "").strip()
                        raw_matching_chunks = candidate.get("matching_chunks")
                        if isinstance(raw_matching_chunks, list):
                            lab_matching_chunk_ids = [
                                str(cid).strip() for cid in raw_matching_chunks if str(cid).strip()
                            ]

                        if test_name and value and date:
                            highlight_term = f"{test_name} {value} {date}"
                        elif test_name and value:
                            highlight_term = f"{test_name} {value}"
                        elif test_name:
                            highlight_term = test_name
            except Exception as e:
                logger.warning(f"Failed to build value-aware lab term: {e}", exc_info=True)

        chunk_data = None
        correct_chunk = None
        correct_page = entity_source.page_number

        from app.repositories.chunk_repository import ChunkRepository
        chunk_repo = ChunkRepository()

        # Prefer matching_chunks from extracted lab item when available.
        if data_type == "lab" and lab_matching_chunk_ids:
            try:
                test_name = str((lab_item or {}).get("test_name") or "").strip().lower()
                value = str((lab_item or {}).get("value") or "").strip().lower()
                date = str((lab_item or {}).get("date") or "").strip().lower()
                best_lab_chunk = None
                best_score = -1
                for chunk_id in lab_matching_chunk_ids:
                    chunk_candidate = chunk_repo.get_by_id(db, chunk_id)
                    if not chunk_candidate or not chunk_candidate.chunk_text:
                        continue
                    text = chunk_candidate.chunk_text.lower()
                    score = 0
                    if test_name and test_name in text:
                        score += 10
                    if value and value in text:
                        score += 8
                    if date and date in text:
                        score += 6
                    if chunk_candidate.id == entity_source.chunk_id:
                        score += 1
                    if score > best_score:
                        best_score = score
                        best_lab_chunk = chunk_candidate
                # IMPORTANT: For repeated same-name labs, don't trust a candidate
                # unless it also matches the numeric value when available.
                value_required = bool(value)
                best_has_value = bool(best_lab_chunk and value and value in (best_lab_chunk.chunk_text or "").lower())
                if best_lab_chunk and best_score > 0 and (not value_required or best_has_value):
                    correct_chunk = best_lab_chunk
                    correct_page = best_lab_chunk.page_number
                else:
                    logger.info(
                        "[EVIDENCE] matching_chunks did not provide value-specific lab chunk for %s; falling back to full-file search",
                        entity_id,
                    )
            except Exception as e:
                logger.warning(f"Failed selecting lab chunk from matching_chunks: {e}", exc_info=True)

        if entity_source.chunk_id and not correct_chunk:
            try:
                chunk = chunk_repo.get_by_id(db, entity_source.chunk_id)
                if chunk:
                    entity_name = highlight_term if data_type == "lab" else (entity_source.snippet or highlight_term or "")
                    entity_name_clean = entity_name.strip().lower()
                    chunk_text_lower = (chunk.chunk_text or "").lower()

                    if entity_name_clean and entity_name_clean in chunk_text_lower:
                        correct_chunk = chunk
                        correct_page = chunk.page_number
            except Exception as e:
                logger.warning(f"Failed to load chunk: {e}", exc_info=True)

        if not correct_chunk and entity_source.file_id:
            try:
                all_chunks = chunk_repo.get_by_file_id(db, entity_source.file_id)
                entity_name = highlight_term if data_type == "lab" else (entity_source.snippet or highlight_term or "")
                entity_name_clean = entity_name.strip().lower()

                if entity_name_clean and all_chunks:
                    best_match = None
                    best_match_score = 0
                    for chunk in all_chunks:
                        if not chunk.chunk_text:
                            continue
                        chunk_text_lower = chunk.chunk_text.lower()

                        if data_type == "lab" and isinstance(lab_item, dict):
                            test_name = str(lab_item.get("test_name") or "").strip().lower()
                            value = str(lab_item.get("value") or "").strip().lower()
                            date = str(lab_item.get("date") or "").strip().lower()
                            score = 0
                            if test_name and test_name in chunk_text_lower:
                                score += 10
                            if value and value in chunk_text_lower:
                                score += 12
                            if date and date in chunk_text_lower:
                                score += 8
                            # Require value hit for repeated-name labs when value exists.
                            if value and value not in chunk_text_lower:
                                continue
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                            continue

                        if entity_name_clean in chunk_text_lower:
                            score = 100 + len(entity_name_clean)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue

                        # Fuzzy match
                        import re
                        def normalize_simple(text):
                            return re.sub(r'[^a-zA-Z0-9]', '', text.lower())

                        norm_entity = normalize_simple(entity_name_clean)
                        norm_chunk = normalize_simple(chunk_text_lower)
                        if norm_entity in norm_chunk:
                            score = 50 + len(norm_entity)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue

                        # Word overlap
                        words = entity_name_clean.split()
                        if len(words) > 1:
                            match_count = sum(1 for word in words if word in chunk_text_lower and len(word) > 2)
                            if match_count >= len(words) * 0.7:
                                score = match_count * 10
                                if score > best_match_score:
                                    best_match_score = score
                                    best_match = chunk

                    if best_match:
                        correct_chunk = best_match
                        correct_page = best_match.page_number
            except Exception as e:
                logger.warning(
                    f"Failed to search for correct chunk: {e}", exc_info=True
                )

        if correct_chunk:
            if data_type == "lab" and getattr(correct_chunk, "word_segments", None):
                try:
                    from app.utils.bbox_utils import find_term_bbox
                    terms_to_try = []
                    if isinstance(lab_item, dict):
                        test_name = str(lab_item.get("test_name") or "").strip()
                        value = str(lab_item.get("value") or "").strip()
                        date = str(lab_item.get("date") or "").strip()
                        unit = str(lab_item.get("unit") or "").strip()
                        reference_range = str(lab_item.get("reference_range") or "").strip()
                        if test_name and value and date:
                            terms_to_try.extend([f"{test_name} {value} {date}", f"{test_name} {date} {value}"])
                        if test_name and value and unit:
                            terms_to_try.append(f"{test_name} {value} {unit}")
                        if test_name and value and reference_range:
                            terms_to_try.append(f"{test_name} {value} {reference_range}")
                        if test_name and value:
                            terms_to_try.append(f"{test_name} {value}")
                    if not terms_to_try and highlight_term:
                        terms_to_try.append(highlight_term)

                    seen_terms = set()
                    for term in terms_to_try:
                        if not term or term in seen_terms:
                            continue
                        seen_terms.add(term)
                        precise_bbox = find_term_bbox(term, correct_chunk.word_segments)
                        if precise_bbox:
                            entity_source.bbox = precise_bbox
                            break
                except Exception as e:
                    logger.warning(f"Failed recalculating lab bbox: {e}", exc_info=True)

            chunk_data = {
                "chunk_id": correct_chunk.id,
                "chunk_text": correct_chunk.chunk_text,
                "char_start": correct_chunk.char_start,
                "char_end": correct_chunk.char_end,
                "section_type": (
                    correct_chunk.section_type.value
                    if hasattr(correct_chunk.section_type, "value")
                    else str(correct_chunk.section_type)
                ),
            }

        source_info = {
            "file_id": entity_source.file_id,
            "file_name": file_name,
            "page": correct_page,
            "bbox": entity_source.bbox,
            "snippet": entity_source.snippet,
            "full_text": entity_source.full_text,
            "term": highlight_term if highlight_term else None,
            "chunk": chunk_data,
        }

        try:
            from app.services.analytics_service import AnalyticsService

            analytics_service = AnalyticsService()
            source_type = "chunk" if entity_source.chunk_id else "file"
            analytics_service.track_evidence_click(
                db=db,
                user_id=case.user_id,
                case_id=case_id,
                entity_type=data_type,
                entity_id=data_id,
                source_type=source_type,
                file_id=entity_source.file_id,
                page_number=entity_source.page_number,
                chunk_id=entity_source.chunk_id,
            )
        except Exception as e:
            logger.warning(f"Failed to track evidence click: {e}", exc_info=True)

        return {"item": {}, "source": source_info}

    # Fallback path
    extraction = extraction_repository.get_by_case_id(db, case_id)
    if not extraction or not extraction.source_mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Source not found for {data_type}:{data_id} in case {case_id}",
        )

    extracted_data = extraction.extracted_data or {}
    source_mapping = extraction.source_mapping
    item = None
    source_info = None

    try:
        index = int(data_id) if data_id.isdigit() else None
    except (ValueError, TypeError):
        index = None

    if data_type == "medication":
        medications = extracted_data.get("medications", [])
        if index is not None and index < len(medications):
            item = medications[index]
            source_file = item.get("source_file")
            source_page = item.get("source_page")
            if source_file and source_page:
                page_num = int(source_page) if str(source_page).isdigit() else 1
                files_list = source_mapping.get("files", [])
                file_id = None
                if isinstance(files_list, list):
                    for file_info in files_list:
                        if (
                            isinstance(file_info, dict)
                            and file_info.get("file_name") == source_file
                        ):
                            file_id = file_info.get("id")
                            break

                file_page_mapping = source_mapping.get("file_page_mapping", {})
                page_text = ""
                if (
                    file_id
                    and isinstance(file_page_mapping, dict)
                    and file_id in file_page_mapping
                ):
                    page_mapping = file_page_mapping[file_id]
                    if isinstance(page_mapping, dict):
                        page_text = page_mapping.get(page_num, "") or page_mapping.get(
                            str(page_num), ""
                        )

                source_info = {
                    "file_id": file_id,
                    "file_name": source_file,
                    "page": page_num,
                    "snippet": (
                        page_text[:500]
                        if page_text
                        else (
                            item.get("name", "")[:500] if isinstance(item, dict) else ""
                        )
                    ),
                    "full_text": page_text,
                    "term": item.get("name") if isinstance(item, dict) else None,
                }

    elif data_type == "lab":
        labs = extracted_data.get("labs", [])
        if index is not None and index < len(labs):
            item = labs[index]
            source_file = item.get("source_file")
            source_page = item.get("source_page")
            if source_file and source_page:
                page_num = int(source_page) if str(source_page).isdigit() else 1
                files_list = source_mapping.get("files", [])
                file_id = None
                if isinstance(files_list, list):
                    for file_info in files_list:
                        if (
                            isinstance(file_info, dict)
                            and file_info.get("file_name") == source_file
                        ):
                            file_id = file_info.get("id")
                            break

                file_page_mapping = source_mapping.get("file_page_mapping", {})
                page_text = ""
                if (
                    file_id
                    and isinstance(file_page_mapping, dict)
                    and file_id in file_page_mapping
                ):
                    page_mapping = file_page_mapping[file_id]
                    if isinstance(page_mapping, dict):
                        page_text = page_mapping.get(page_num, "") or page_mapping.get(
                            str(page_num), ""
                        )

                source_info = {
                    "file_id": file_id,
                    "file_name": source_file,
                    "page": page_num,
                    "snippet": (
                        page_text[:500]
                        if page_text
                        else (
                            item.get("test_name", "")[:500]
                            if isinstance(item, dict)
                            else ""
                        )
                    ),
                    "full_text": page_text,
                    "term": item.get("test_name") if isinstance(item, dict) else None,
                }

    elif data_type == "diagnosis":
        diagnoses = extracted_data.get("diagnoses", [])
        if index is not None and index < len(diagnoses):
            item = diagnoses[index]
            source_file = item.get("source_file")
            source_page = item.get("source_page")
            files_list = (
                source_mapping.get("files", [])
                if isinstance(source_mapping, dict)
                else []
            )
            file_id = None
            file_name = None
            page_num = 1

            if source_file and source_page:
                page_num = int(source_page) if str(source_page).isdigit() else 1
                for file_info in files_list:
                    if (
                        isinstance(file_info, dict)
                        and file_info.get("file_name") == source_file
                    ):
                        file_id = file_info.get("id")
                        file_name = file_info.get("file_name")
                        break
            elif files_list:
                first = files_list[0]
                if isinstance(first, dict):
                    file_id = first.get("id")
                    file_name = first.get("file_name")

            file_page_mapping = (
                source_mapping.get("file_page_mapping", {})
                if isinstance(source_mapping, dict)
                else {}
            )
            page_text = ""
            if (
                file_id
                and isinstance(file_page_mapping, dict)
                and file_id in file_page_mapping
            ):
                page_mapping = file_page_mapping[file_id]
                if isinstance(page_mapping, dict):
                    page_text = page_mapping.get(page_num, "") or page_mapping.get(
                        str(page_num), ""
                    )

            source_info = {
                "file_id": file_id,
                "file_name": file_name or source_file or "Source document",
                "page": page_num,
                "snippet": (
                    page_text[:500]
                    if page_text
                    else (
                        item.get("name", "")[:500]
                        if isinstance(item, dict)
                        else "Diagnosis extracted from case documents"
                    )
                ),
                "full_text": page_text or "",
                "term": item.get("name") if isinstance(item, dict) else None,
            }

    if not source_info or not source_info.get("file_id"):
        raise HTTPException(
            status_code=404,
            detail=f"Source not found for {data_type}:{data_id} in case {case_id}. Missing file_id.",
        )

    if not source_info.get("term"):
        source_info["term"] = source_validation_service.extract_highlight_term(
            snippet=source_info.get("snippet"),
            entity_type=data_type,
        )

    try:
        from app.services.analytics_service import AnalyticsService

        analytics_service = AnalyticsService()
        analytics_service.track_evidence_click(
            db=db,
            user_id=case.user_id,
            case_id=case_id,
            entity_type=data_type,
            entity_id=data_id,
            source_type="file",
            file_id=source_info.get("file_id"),
            page_number=source_info.get("page"),
        )
    except Exception as e:
        logger.warning(f"Failed to track evidence click: {e}", exc_info=True)

    return {"item": item or {}, "source": source_info}



@router.get("/cases/{case_id}/files/{file_id}/page/{page}")
async def get_file_page(
    case_id: str,
    file_id: str,
    page: int,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
):
    """Get text for specific page of a file"""
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_file = case_file_repository.get_by_case_and_file_id(db, case_id, file_id)

    if not case_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Extract text from the specific page
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
    use_proxy: bool = False,  # Query parameter to force backend streaming (for CORS issues)
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    case_file_repository: CaseFileRepository = Depends(get_case_file_repository),
):
    """Get PDF file - supports both pre-signed URLs and backend streaming

    For S3:
    - By default: Returns pre-signed URL for direct browser access (requires S3 CORS configuration)
    - If use_proxy=true: Streams through backend to avoid CORS issues

    For local: Always streams through backend
    """
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case_file = case_file_repository.get_by_case_and_file_id(db, case_id, file_id)
    if not case_file:
        raise HTTPException(status_code=404, detail="File not found")

    if not case_file.file_path:
        raise HTTPException(status_code=404, detail="File path not found")

    # In S3 mode, check if we should proxy through backend
    if settings.STORAGE_TYPE == "s3":
        if use_proxy:
            # Stream through backend to avoid CORS issues
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
                logger.error(
                    f"Failed to retrieve PDF from S3 for {case_file.file_path}: {e}"
                )
                raise HTTPException(
                    status_code=500, detail="Failed to retrieve PDF document."
                )
        else:
            # Return pre-signed URL (requires S3 CORS configuration)
            from app.services.s3_storage_service import s3_storage_service

            try:
                presigned_url = s3_storage_service.get_file_url(
                    case_file.file_path, expires_in=3600
                )
                return {
                    "url": presigned_url,
                    "file_name": case_file.file_name,
                    "expires_in": 3600,
                    "proxy_url": f"/api/v1/cases/{case_id}/files/{file_id}/pdf?use_proxy=true",  # Fallback URL
                }
            except Exception as e:
                logger.error(
                    f"Failed to generate pre-signed URL for {case_file.file_path}: {e}"
                )
                raise HTTPException(
                    status_code=500, detail="Failed to generate PDF access URL."
                )

    # Legacy/Local fallback: stream through backend
    if not os.path.exists(case_file.file_path):
        raise HTTPException(status_code=404, detail=f"Source file not found on server.")

    return FileResponse(
        path=case_file.file_path,
        media_type="application/pdf",
        filename=case_file.file_name,
    )


@router.get("/cases/{case_id}/sources/{entity_type}/{entity_id}")
async def get_entity_source(
    case_id: str,
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    case_repository: CaseRepository = Depends(get_case_repository),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
    entity_source_service: EntitySourceService = Depends(get_entity_source_service),
):
    """
    Get source information for an entity (industry-standard source resolution).

    This is the single source of truth for entity source information.
    Falls back to extraction.source_mapping if EntitySource doesn't exist.

    Args:
        case_id: Case ID
        entity_type: Type of entity ('medication', 'lab', 'timeline', 'diagnosis', 'vital', etc.)
        entity_id: Entity identifier (e.g., 'medication:0', 'timeline:abc123', 'lab:5')
                   May be URL encoded (e.g., 'diagnosis%3A0')

    Returns:
        Source information with file_id, page_number, bbox, snippet, etc.
    """
    logger.info(
        f"[EVIDENCE] get_entity_source called: case_id={case_id}, entity_type={entity_type}, entity_id={entity_id}"
    )

    # Verify case exists and get user_id
    case = case_repository.get_by_id(db, case_id)
    if not case:
        logger.error(f"[EVIDENCE] Case not found: case_id={case_id}")
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # URL decode entity_id if needed
    import urllib.parse

    original_entity_id = entity_id
    entity_id = urllib.parse.unquote(entity_id)
    if original_entity_id != entity_id:
        logger.debug(
            f"[EVIDENCE] URL decoded entity_id: {original_entity_id} -> {entity_id}"
        )

    logger.info(
        f"[EVIDENCE] Querying EntitySource: case_id={case_id}, entity_type={entity_type}, entity_id={entity_id}, user_id={case.user_id}"
    )

    # Get entity source
    entity_source = entity_source_service.get_entity_source(
        db=db,
        case_id=case_id,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=case.user_id,
    )

    if entity_source:
        # CRITICAL: Log EntitySource details immediately
        logger.info(
            f"[EVIDENCE] EntitySource found (PRIMARY PATH): entity_type={entity_type}, entity_id={entity_id}, file_id={entity_source.file_id}, page={entity_source.page_number}, has_bbox={entity_source.bbox is not None}, has_chunk_id={entity_source.chunk_id is not None}, chunk_id={entity_source.chunk_id}"
        )
        print(
            f"[EVIDENCE] EntitySource found: chunk_id={entity_source.chunk_id}, file_id={entity_source.file_id}, page={entity_source.page_number}"
        )  # Also print to stdout for visibility

        # CRITICAL: Initialize chunk_data to ensure it's always set
        chunk_data = None
        # Found in EntitySource - use it
        file_name = None
        if entity_source.file_id:
            case_file_repo = CaseFileRepository()
            case_file = case_file_repo.get_by_id(db, entity_source.file_id)
            if case_file:
                file_name = case_file.file_name

        # Extract highlight term using centralized service
        highlight_term = None
        lab_item = None
        lab_matching_chunk_ids = []

        if entity_type == "timeline":
            # For timeline events, get the actual event description from the extraction
            event_id = (
                entity_id.replace("timeline:", "")
                if entity_id.startswith("timeline:")
                else entity_id
            )
            description = source_validation_service.get_timeline_event_description(
                db, case_id, event_id
            )
            highlight_term = source_validation_service.extract_highlight_term(
                description=description,
                snippet=entity_source.snippet,
                entity_type="timeline",
            )
        else:
            # For non-timeline entities, extract from snippet.
            # entity_type is forwarded so that diagnoses/procedures get their
            # full canonical name returned instead of a truncated substring.
            highlight_term = source_validation_service.extract_highlight_term(
                snippet=entity_source.snippet,
                entity_type=entity_type,
            )

        # For labs with repeated test names on the same page (e.g., multiple WBC
        # values across dates), disambiguate using test_name + value (+ date).
        # This prevents "WBC" from always highlighting the first row occurrence.
        if entity_type == "lab":
            try:
                extraction = extraction_repository.get_by_case_id(db, case_id)
                labs = (
                    (extraction.extracted_data or {}).get("labs", [])
                    if extraction and isinstance(extraction.extracted_data, dict)
                    else []
                )
                lab_index = None
                if ":" in entity_id:
                    suffix = entity_id.split(":", 1)[1]
                    if suffix.isdigit():
                        lab_index = int(suffix)
                elif str(entity_id).isdigit():
                    lab_index = int(entity_id)

                if lab_index is not None and 0 <= lab_index < len(labs):
                    candidate = labs[lab_index]
                    if isinstance(candidate, dict):
                        lab_item = candidate
                        raw_matching_chunks = candidate.get("matching_chunks")
                        if isinstance(raw_matching_chunks, list):
                            lab_matching_chunk_ids = [
                                str(cid).strip() for cid in raw_matching_chunks if str(cid).strip()
                            ]
                        test_name = str(candidate.get("test_name") or "").strip()
                        value = str(candidate.get("value") or "").strip()
                        date = str(candidate.get("date") or "").strip()
                        # Prefer value-aware term; include date to further reduce
                        # collisions when many same-name values appear.
                        if test_name and value and date:
                            highlight_term = f"{test_name} {value} {date}"
                        elif test_name and value:
                            highlight_term = f"{test_name} {value}"
                        elif test_name:
                            highlight_term = test_name
                        logger.info(
                            "[EVIDENCE] Lab disambiguation term for %s: '%s' (index=%s, value=%s, date=%s)",
                            entity_id,
                            (highlight_term or "")[:120],
                            lab_index,
                            value,
                            date,
                        )
            except Exception as e:
                logger.warning(
                    f"[EVIDENCE] Could not build value-aware lab highlight term for {entity_id}: {e}"
                )

        # Get chunk data if chunk_id exists (for text-based highlighting)
        # CRITICAL: Validate chunk contains entity text and find correct page
        chunk_data = None
        correct_chunk = None
        correct_page = entity_source.page_number  # Default to EntitySource page

        from app.repositories.chunk_repository import ChunkRepository

        chunk_repo = ChunkRepository()

        # For labs, prefer chunk candidates from extracted item metadata when available.
        # This helps recover when persisted EntitySource points to a generic same-name
        # chunk (e.g., first "WBC"), while matching_chunks include the specific row/day.
        if entity_type == "lab" and lab_item and lab_matching_chunk_ids:
            try:
                test_name = str(lab_item.get("test_name") or "").strip().lower()
                value = str(lab_item.get("value") or "").strip().lower()
                date = str(lab_item.get("date") or "").strip().lower()
                best_lab_chunk = None
                best_lab_score = -1

                for chunk_id in lab_matching_chunk_ids:
                    chunk_candidate = chunk_repo.get_by_id(db, chunk_id)
                    if not chunk_candidate or not chunk_candidate.chunk_text:
                        continue
                    text = chunk_candidate.chunk_text.lower()
                    score = 0
                    if test_name and test_name in text:
                        score += 10
                    if value and value in text:
                        score += 8
                    if date and date in text:
                        score += 6
                    if chunk_candidate.id == entity_source.chunk_id:
                        score += 1
                    if score > best_lab_score:
                        best_lab_score = score
                        best_lab_chunk = chunk_candidate

                if best_lab_chunk and best_lab_score > 0:
                    correct_chunk = best_lab_chunk
                    correct_page = best_lab_chunk.page_number
                    logger.info(
                        "[EVIDENCE] Selected lab chunk from matching_chunks for %s: chunk_id=%s page=%s score=%s",
                        entity_id,
                        best_lab_chunk.id,
                        best_lab_chunk.page_number,
                        best_lab_score,
                    )
            except Exception as e:
                logger.warning(
                    f"[EVIDENCE] Failed selecting lab chunk from matching_chunks for {entity_id}: {e}"
                )

        if entity_source.chunk_id and not correct_chunk:
            logger.info(
                f"[EVIDENCE] EntitySource has chunk_id={entity_source.chunk_id}, attempting to load chunk data"
            )
            print(
                f"[EVIDENCE] Loading chunk: chunk_id={entity_source.chunk_id}"
            )  # Print for visibility
            try:
                chunk = chunk_repo.get_by_id(db, entity_source.chunk_id)
                print(
                    f"[EVIDENCE] Chunk lookup result: found={chunk is not None}, chunk_id={chunk.id if chunk else None}"
                )  # Print for visibility
                if chunk:
                    # CRITICAL: Validate that chunk actually contains the entity text
                    entity_name = entity_source.snippet or highlight_term or ""
                    entity_name_clean = entity_name.strip().lower()
                    chunk_text_lower = (chunk.chunk_text or "").lower()

                    # Check if entity name appears in chunk text
                    if entity_name_clean and entity_name_clean in chunk_text_lower:
                        # Chunk is correct - use it
                        correct_chunk = chunk
                        correct_page = chunk.page_number
                        logger.info(
                            f"[EVIDENCE] ✅ Linked chunk contains entity text: chunk_id={chunk.id}, page={chunk.page_number}"
                        )
                        print(
                            f"[EVIDENCE] ✅ Linked chunk is correct: page={chunk.page_number}"
                        )
                    else:
                        # Chunk doesn't contain entity text - need to find correct chunk
                        logger.warning(
                            f"[EVIDENCE] ⚠️ Linked chunk (page {chunk.page_number}) doesn't contain entity text '{entity_name_clean[:50]}...' - searching for correct chunk"
                        )
                        print(
                            f"[EVIDENCE] ⚠️ Linked chunk (page {chunk.page_number}) doesn't contain '{entity_name_clean[:30]}...' - searching..."
                        )
                        correct_chunk = None
                else:
                    logger.warning(
                        f"[EVIDENCE] ⚠️ EntitySource has chunk_id={entity_source.chunk_id} but chunk not found in database - will try fallback"
                    )
            except Exception as e:
                logger.error(
                    f"[EVIDENCE] ❌ Error loading chunk by chunk_id={entity_source.chunk_id}: {e}",
                    exc_info=True,
                )
                # Continue to fallback

        # If linked chunk is wrong or missing, search for correct chunk
        if not correct_chunk and entity_source.file_id:
            logger.info(
                f"[EVIDENCE] Searching for correct chunk containing entity text in file_id={entity_source.file_id}"
            )
            try:
                # Get all chunks for this file
                all_chunks = chunk_repo.get_by_file_id(db, entity_source.file_id)
                entity_name = entity_source.snippet or highlight_term or ""
                entity_name_clean = entity_name.strip().lower()

                if entity_name_clean and all_chunks:
                    import re
                    # Normalize for fuzzy matching: remove non-alphanumeric and extra whitespace
                    def normalize_text(text):
                        return re.sub(r'[^a-zA-Z0-9]', '', text.lower())
                    
                    norm_entity_name = normalize_text(entity_name_clean)
                    logger.info(
                        f"[EVIDENCE] Searching {len(all_chunks)} chunks using fuzzy normalization: '{norm_entity_name[:30]}...'"
                    )
                    
                    best_match = None
                    best_match_score = 0

                    for chunk in all_chunks:
                        if not chunk.chunk_text:
                            continue
                        chunk_text_lower = chunk.chunk_text.lower()
                        
                        # 1. Exact match (preferred)
                        if entity_name_clean in chunk_text_lower:
                            score = 100 + len(entity_name_clean)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue
                                
                        # 2. Fuzzy match (normalized)
                        norm_chunk_text = normalize_text(chunk_text_lower)
                        if norm_entity_name in norm_chunk_text:
                            score = len(norm_entity_name)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk

                    if best_match:
                        correct_chunk = best_match
                        correct_page = best_match.page_number
                        logger.info(
                            f"[EVIDENCE] ✅ Found correct chunk: chunk_id={best_match.id}, page={best_match.page_number} (was linked to page {entity_source.page_number})"
                        )
                        print(
                            f"[EVIDENCE] ✅ Found correct chunk: page={best_match.page_number} (was {entity_source.page_number})"
                        )
                    else:
                        logger.warning(
                            f"[EVIDENCE] ⚠️ Could not find chunk containing entity text '{entity_name_clean[:50]}...' - using linked chunk/page"
                        )
                        # Fallback to EntitySource page_number
                        if entity_source.page_number:
                            chunks = chunk_repo.get_by_page(
                                db, entity_source.file_id, entity_source.page_number
                            )
                            if chunks:
                                correct_chunk = chunks[0]
                                correct_page = entity_source.page_number
                                logger.info(
                                    f"[EVIDENCE] Using fallback: first chunk on page {entity_source.page_number}"
                                )
            except Exception as e:
                logger.error(
                    f"[EVIDENCE] ❌ Error searching for correct chunk: {e}",
                    exc_info=True,
                )

        # Build chunk_data if we have a chunk
        if correct_chunk:
            # For labs, try to recalculate a row-specific bbox from word-level
            # segments using value/date-aware terms. This fixes repeated test-name
            # rows on the same page that would otherwise all highlight first match.
            if entity_type == "lab" and getattr(correct_chunk, "word_segments", None):
                try:
                    from app.utils.bbox_utils import find_term_bbox

                    terms_to_try = []
                    if isinstance(lab_item, dict):
                        test_name = str(lab_item.get("test_name") or "").strip()
                        value = str(lab_item.get("value") or "").strip()
                        date = str(lab_item.get("date") or "").strip()
                        unit = str(lab_item.get("unit") or "").strip()
                        reference_range = str(lab_item.get("reference_range") or "").strip()

                        has_value_aware_term = bool(test_name and value)
                        if test_name and value and date:
                            terms_to_try.append(f"{test_name} {value} {date}")
                            terms_to_try.append(f"{test_name} {date} {value}")
                        if test_name and value and unit:
                            terms_to_try.append(f"{test_name} {value} {unit}")
                        if test_name and value and reference_range:
                            terms_to_try.append(f"{test_name} {value} {reference_range}")
                        if test_name and value:
                            terms_to_try.append(f"{test_name} {value}")
                        # Avoid plain-name fallback for repeated-name labs when a
                        # value-aware term exists; plain "WBC" reintroduces false
                        # first-row highlights.
                        if test_name and not has_value_aware_term:
                            terms_to_try.append(test_name)
                    elif highlight_term:
                        terms_to_try.append(highlight_term)

                    # De-duplicate while preserving order.
                    seen = set()
                    ordered_terms = []
                    for t in terms_to_try:
                        if t and t not in seen:
                            ordered_terms.append(t)
                            seen.add(t)

                    for term in ordered_terms:
                        precise_bbox = find_term_bbox(term, correct_chunk.word_segments)
                        if precise_bbox:
                            entity_source.bbox = precise_bbox
                            # Only override term when no term exists. Keep the
                            # disambiguated value/date-aware term if already set.
                            if not highlight_term:
                                highlight_term = term
                            logger.info(
                                "[EVIDENCE] Using value-aware lab bbox term '%s' for %s",
                                term[:80],
                                entity_id,
                            )
                            break
                except Exception as e:
                    logger.warning(
                        f"[EVIDENCE] Failed recalculating lab bbox for {entity_id}: {e}"
                    )

            chunk_data = {
                "chunk_id": correct_chunk.id,
                "chunk_text": correct_chunk.chunk_text,
                "char_start": correct_chunk.char_start,
                "char_end": correct_chunk.char_end,
                "section_type": (
                    correct_chunk.section_type.value
                    if hasattr(correct_chunk.section_type, "value")
                    else str(correct_chunk.section_type)
                ),
            }
            # Use chunk bbox if EntitySource bbox is missing
            if not entity_source.bbox and correct_chunk.bbox:
                logger.debug(
                    f"[EVIDENCE] Using bbox from chunk (EntitySource bbox was missing)"
                )
                entity_source.bbox = correct_chunk.bbox

        if not chunk_data:
            logger.warning(
                f"[EVIDENCE] ⚠️ No chunk data available after all attempts - EntitySource.chunk_id={entity_source.chunk_id}, file_id={entity_source.file_id}, page={entity_source.page_number}"
            )
            print(
                f"[EVIDENCE] ⚠️ No chunk data: chunk_id={entity_source.chunk_id}, file_id={entity_source.file_id}, page={entity_source.page_number}"
            )  # Print for visibility

        # Log page correction if it changed
        if correct_page != entity_source.page_number:
            logger.warning(
                f"[EVIDENCE] ⚠️ Page corrected: EntitySource.page_number={entity_source.page_number} -> correct_page={correct_page} (entity found in chunk on page {correct_page})"
            )
            print(
                f"[EVIDENCE] ⚠️ Page corrected: {entity_source.page_number} -> {correct_page}"
            )

        # Build response
        # CRITICAL: Use correct_page (from chunk validation) instead of entity_source.page_number
        # This ensures we open the correct page where the entity actually appears
        source_info = {
            "file_id": entity_source.file_id,
            "file_name": file_name,
            "page": correct_page,  # Use correct page from chunk validation
            "bbox": entity_source.bbox,
            "snippet": entity_source.snippet,
            "full_text": entity_source.full_text,
            "term": highlight_term if highlight_term else None,
        }

        # CRITICAL: Add chunk data separately to ensure it's included
        # ALWAYS include chunk field (even if None) so frontend knows the state
        # FastAPI will serialize None as null in JSON, which is what we want
        source_info["chunk"] = chunk_data  # This will be None if chunk_data is None

        # Log chunk status for debugging
        if chunk_data:
            logger.info(
                f"[EVIDENCE] ✅ Added chunk to source_info: chunk_id={chunk_data.get('chunk_id')}, text_length={len(chunk_data.get('chunk_text', '')) if chunk_data.get('chunk_text') else 0}"
            )
        else:
            logger.warning(
                f"[EVIDENCE] ⚠️ chunk_data is None - setting source_info['chunk'] = None (EntitySource.chunk_id={entity_source.chunk_id})"
            )

        # CRITICAL: Verify chunk key is in source_info before proceeding
        if "chunk" not in source_info:
            logger.error(
                f"[EVIDENCE] ❌ CRITICAL ERROR: 'chunk' key missing from source_info! Keys: {list(source_info.keys())}"
            )
            # Force add it
            source_info["chunk"] = chunk_data
            logger.info(f"[EVIDENCE] Fixed: Added 'chunk' key to source_info")

        logger.info(
            f"[EVIDENCE] Building response from EntitySource: file_id={source_info['file_id']}, file_name={source_info['file_name']}, page={source_info['page']}, has_bbox={source_info['bbox'] is not None}, has_term={source_info['term'] is not None}, has_chunk={chunk_data is not None}, chunk_in_dict={'chunk' in source_info}"
        )

        # Validate source data
        if entity_source.file_id and entity_source.page_number:
            logger.debug(
                f"[EVIDENCE] Validating source: file_id={entity_source.file_id}, page={entity_source.page_number}"
            )
            is_valid, error_msg, max_page = (
                source_validation_service.validate_file_and_page(
                    db, case_id, entity_source.file_id, entity_source.page_number
                )
            )
            if not is_valid:
                logger.warning(
                    f"[EVIDENCE] Source validation failed: {error_msg} (entity_type={entity_type}, entity_id={entity_id}, file_id={entity_source.file_id}, page={entity_source.page_number}, max_page={max_page})"
                )
            else:
                logger.debug(
                    f"[EVIDENCE] Source validation passed: file_id={entity_source.file_id}, page={entity_source.page_number}"
                )

        # Track evidence click for analytics
        try:
            from app.services.analytics_service import AnalyticsService

            analytics_service = AnalyticsService()
            source_type = "chunk" if entity_source.chunk_id else "file"
            analytics_service.track_evidence_click(
                db=db,
                user_id=case.user_id,
                case_id=case_id,
                entity_type=entity_type,
                entity_id=entity_id,
                source_type=source_type,
                file_id=entity_source.file_id,
                page_number=entity_source.page_number,
                chunk_id=entity_source.chunk_id,
            )
        except Exception as e:
            logger.warning(
                f"Failed to track evidence click for entity source: {e}", exc_info=True
            )

        # Final verification before returning
        logger.info(
            f"[EVIDENCE] Final response check - source_info keys: {list(source_info.keys())}, has_chunk_key: {'chunk' in source_info}, chunk_value: {source_info.get('chunk') is not None if 'chunk' in source_info else 'KEY_MISSING'}"
        )

        # CRITICAL: Force include chunk field (even if None) - ALWAYS include it
        # FastAPI will serialize None as null in JSON, which is what we want
        source_info["chunk"] = chunk_data  # Force set it to ensure it's always present
        print(
            f"[EVIDENCE] Before response_data: source_info keys={list(source_info.keys())}, chunk in dict={'chunk' in source_info}, chunk_value={source_info.get('chunk')}"
        )  # Print for visibility

        # CRITICAL: Build response_data with chunk explicitly included
        # Use dict() constructor to ensure all fields are included
        response_data = {
            "item": {
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
            "source": {
                "file_id": source_info.get("file_id"),
                "file_name": source_info.get("file_name"),
                "page": source_info.get("page"),
                "bbox": source_info.get("bbox"),
                "snippet": source_info.get("snippet"),
                "full_text": source_info.get("full_text"),
                "term": source_info.get("term"),
                "chunk": chunk_data,  # EXPLICITLY include chunk field
            },
        }
        print(
            f"[EVIDENCE] After response_data: source keys={list(response_data['source'].keys())}, chunk in response={'chunk' in response_data['source']}, chunk_value={response_data['source'].get('chunk')}"
        )  # Print for visibility

        # Triple-check chunk is in response
        if "chunk" not in response_data["source"]:
            logger.error(
                f"[EVIDENCE] ❌ CRITICAL: 'chunk' key STILL missing after all attempts! Forcing it now."
            )
            print(
                f"[EVIDENCE] ❌ ERROR: chunk key missing from response! Forcing it now."
            )
            response_data["source"]["chunk"] = chunk_data

        chunk_val = response_data["source"]["chunk"]
        if chunk_val is not None:
            logger.info(
                f"[EVIDENCE] ✅ Chunk in response: type={type(chunk_val)}, chunk_id={chunk_val.get('chunk_id') if isinstance(chunk_val, dict) else 'N/A'}, text_length={len(chunk_val.get('chunk_text', '')) if isinstance(chunk_val, dict) else 0}"
            )
            print(
                f"[EVIDENCE] ✅ Chunk in response: chunk_id={chunk_val.get('chunk_id') if isinstance(chunk_val, dict) else 'N/A'}"
            )
        else:
            logger.warning(
                f"[EVIDENCE] ⚠️ Chunk in response but value is None (chunk_data was None)"
            )
            print(f"[EVIDENCE] ⚠️ Chunk in response but value is None")

        # Final log with response structure
        logger.info(
            f"[EVIDENCE] Backend: Returning source info for {entity_type}:{entity_id} with file_id={source_info.get('file_id')}, page={source_info.get('page')}, bbox_present={bool(source_info.get('bbox'))}, chunk_present={chunk_data is not None}, chunk_in_response={'chunk' in response_data['source']}"
        )
        # CRITICAL: Print to stdout for immediate visibility
        print(
            f"[EVIDENCE] FINAL RETURN: chunk_present={chunk_data is not None}, chunk_in_response={'chunk' in response_data['source']}, chunk_value={response_data['source'].get('chunk') is not None if 'chunk' in response_data['source'] else 'MISSING'}"
        )

        # CRITICAL: Use JSONResponse to ensure chunk field is included (even if None)
        # This prevents FastAPI from filtering out None values
        return JSONResponse(content=response_data)

    # Fallback: Try extraction.source_mapping (for cases processed before EntitySource)
    logger.warning(
        f"[EVIDENCE] EntitySource not found (FALLBACK PATH): entity_type={entity_type}, entity_id={entity_id}, falling back to extraction.source_mapping"
    )
    extraction = extraction_repository.get_by_case_id(db, case_id)

    if not extraction:
        logger.error(f"[EVIDENCE] Extraction not found: case_id={case_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Source not found for {entity_type}:{entity_id} in case {case_id}",
        )

    if not extraction.source_mapping:
        logger.error(
            f"[EVIDENCE] source_mapping not found in extraction: case_id={case_id}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Source not found for {entity_type}:{entity_id} in case {case_id}",
        )

    logger.info(
        f"[EVIDENCE] Using fallback path: extraction.source_mapping exists, has_file_page_mapping={bool(extraction.source_mapping.get('file_page_mapping'))}, has_files={bool(extraction.source_mapping.get('files'))}"
    )

    # Extract index from entity_id (e.g., "diagnosis:0" -> 0)
    try:
        if ":" in entity_id:
            parts = entity_id.split(":", 1)
            if parts[0] == entity_type:
                index = int(parts[1]) if parts[1].isdigit() else None
            else:
                index = None
        else:
            index = int(entity_id) if entity_id.isdigit() else None
    except (ValueError, TypeError) as e:
        logger.error(
            f"[EVIDENCE] Failed to parse entity_id index: entity_id={entity_id}, error={e}"
        )
        index = None

    if index is None:
        logger.error(
            f"[EVIDENCE] Invalid entity_id format: entity_id={entity_id}, entity_type={entity_type}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Invalid entity_id format: {entity_id}. Expected format: '{entity_type}:index' or 'index'",
        )

    logger.info(f"[EVIDENCE] Parsed index from entity_id: {entity_id} -> index={index}")

    # Get source from extraction.source_mapping
    extracted_data = extraction.extracted_data or {}
    source_mapping = extraction.source_mapping
    source_info = None

    if entity_type == "medication":
        medications = extracted_data.get("medications", [])
        if index < len(medications):
            item = medications[index]
            source_file = item.get("source_file")
            source_page = item.get("source_page")
            if source_file and source_page:
                page_num = (
                    int(source_page)
                    if isinstance(source_page, (int, str))
                    and str(source_page).isdigit()
                    else 1
                )
                files_list = source_mapping.get("files", [])
                file_id = None
                if isinstance(files_list, list):
                    for file_info in files_list:
                        if (
                            isinstance(file_info, dict)
                            and file_info.get("file_name") == source_file
                        ):
                            file_id = file_info.get("id")
                            break

                file_page_mapping = source_mapping.get("file_page_mapping", {})
                page_text = ""
                if (
                    file_id
                    and isinstance(file_page_mapping, dict)
                    and file_id in file_page_mapping
                ):
                    page_mapping = file_page_mapping[file_id]
                    if isinstance(page_mapping, dict):
                        page_text = page_mapping.get(page_num, "") or page_mapping.get(
                            str(page_num), ""
                        )

                source_info = {
                    "file_id": file_id,
                    "file_name": source_file,
                    "page": page_num,
                    "snippet": (
                        page_text[:500]
                        if page_text
                        else (
                            item.get("name", "")[:500] if isinstance(item, dict) else ""
                        )
                    ),
                    "full_text": page_text,
                    "term": item.get("name") if isinstance(item, dict) else None,
                }

    elif entity_type == "lab":
        labs = extracted_data.get("labs", [])
        if index < len(labs):
            item = labs[index]
            source_file = item.get("source_file")
            source_page = item.get("source_page")
            if source_file and source_page:
                page_num = (
                    int(source_page)
                    if isinstance(source_page, (int, str))
                    and str(source_page).isdigit()
                    else 1
                )
                files_list = source_mapping.get("files", [])
                file_id = None
                if isinstance(files_list, list):
                    for file_info in files_list:
                        if (
                            isinstance(file_info, dict)
                            and file_info.get("file_name") == source_file
                        ):
                            file_id = file_info.get("id")
                            break

                file_page_mapping = source_mapping.get("file_page_mapping", {})
                page_text = ""
                if (
                    file_id
                    and isinstance(file_page_mapping, dict)
                    and file_id in file_page_mapping
                ):
                    page_mapping = file_page_mapping[file_id]
                    if isinstance(page_mapping, dict):
                        page_text = page_mapping.get(page_num, "") or page_mapping.get(
                            str(page_num), ""
                        )

                source_info = {
                    "file_id": file_id,
                    "file_name": source_file,
                    "page": page_num,
                    "snippet": (
                        page_text[:500]
                        if page_text
                        else (
                            item.get("test_name", "")[:500]
                            if isinstance(item, dict)
                            else ""
                        )
                    ),
                    "full_text": page_text,
                    "term": item.get("test_name") if isinstance(item, dict) else None,
                }

    elif entity_type == "diagnosis":
        diagnoses = extracted_data.get("diagnoses", [])
        if index < len(diagnoses):
            item = diagnoses[index]
            source_file = item.get("source_file")
            source_page = item.get("source_page")

            files_list = (
                source_mapping.get("files", [])
                if isinstance(source_mapping, dict)
                else []
            )
            file_id = None
            file_name = None
            page_num = 1  # Default to page 1

            if source_file and source_page:
                page_num = (
                    int(source_page)
                    if isinstance(source_page, (int, str))
                    and str(source_page).isdigit()
                    else 1
                )
                for file_info in files_list:
                    if (
                        isinstance(file_info, dict)
                        and file_info.get("file_name") == source_file
                    ):
                        file_id = file_info.get("id")
                        file_name = file_info.get("file_name")
                        break

            # Fallback: use first file if file_id not found
            if not file_id and files_list:
                first = files_list[0]
                if isinstance(first, dict):
                    file_id = first.get("id")
                    file_name = first.get("file_name")
                    # If we had a source_page, use it; otherwise default to 1
                    if source_page:
                        page_num = (
                            int(source_page)
                            if isinstance(source_page, (int, str))
                            and str(source_page).isdigit()
                            else 1
                        )
                    else:
                        page_num = 1

            # If still no file_id, try to find any file in the case
            if not file_id:
                case_file_repo = CaseFileRepository()
                case_files = case_file_repo.list_by_case(db, case_id)
                if case_files:
                    first_file = case_files[0]
                    file_id = first_file.id
                    file_name = first_file.file_name
                    page_num = (
                        int(source_page)
                        if source_page
                        and isinstance(source_page, (int, str))
                        and str(source_page).isdigit()
                        else 1
                    )

            file_page_mapping = (
                source_mapping.get("file_page_mapping", {})
                if isinstance(source_mapping, dict)
                else {}
            )
            page_text = ""
            if (
                file_id
                and isinstance(file_page_mapping, dict)
                and file_id in file_page_mapping
            ):
                page_mapping = file_page_mapping[file_id]
                if isinstance(page_mapping, dict):
                    page_text = page_mapping.get(page_num, "") or page_mapping.get(
                        str(page_num), ""
                    )

            source_info = {
                "file_id": file_id,
                "file_name": file_name or source_file or "Source document",
                "page": page_num,
                "snippet": (
                    page_text[:500]
                    if page_text
                    else (
                        item.get("name", "")[:500]
                        if isinstance(item, dict)
                        else "Diagnosis extracted from case documents"
                    )
                ),
                "full_text": page_text or "",
                "term": item.get("name") if isinstance(item, dict) else None,
            }

    elif entity_type == "timeline":
        # Robust timeline event searching (handles list and dict formats)
        timeline_data = extracted_data.get("timeline") or getattr(extraction, "timeline", None)
        timeline_events = []
        
        if isinstance(timeline_data, list):
            timeline_events = timeline_data
        elif isinstance(timeline_data, dict):
            timeline_events = timeline_data.get("detailed", []) + timeline_data.get("summary", [])
            
        # Clean the search index/id
        clean_index = str(index).replace("timeline:", "")
        
        event = next(
            (
                e
                for e in timeline_events
                if isinstance(e, dict)
                and (
                    str(e.get("id")) == str(clean_index)
                    or str(e.get("id")) == f"timeline:{clean_index}"
                    or str(e.get("id")).endswith(str(clean_index))
                )
            ),
            None,
        )

        if event:
            source_file = event.get("source_file")
            source_page = event.get("source_page") or event.get("page_number")
            file_id = None
            file_name = None
            page_num = 1

            if source_file and source_page:
                page_num = int(source_page) if str(source_page).isdigit() else 1
                files_list = source_mapping.get("files", [])
                if isinstance(files_list, list):
                    for file_info in files_list:
                        if (
                            isinstance(file_info, dict)
                            and file_info.get("file_name") == source_file
                        ):
                            file_id = file_info.get("id")
                            file_name = file_info.get("file_name")
                            break

            # Fallback: first file
            if not file_id:
                files_list = source_mapping.get("files", [])
                if files_list and isinstance(files_list[0], dict):
                    file_id = files_list[0].get("id")
                    file_name = files_list[0].get("file_name")

            file_page_mapping = source_mapping.get("file_page_mapping", {})
            page_text = ""
            if (
                file_id
                and isinstance(file_page_mapping, dict)
                and file_id in file_page_mapping
            ):
                page_mapping = file_page_mapping[file_id]
                if isinstance(page_mapping, dict):
                    page_text = page_mapping.get(page_num, "") or page_mapping.get(
                        str(page_num), ""
                    )

            source_info = {
                "file_id": file_id,
                "file_name": file_name or source_file or "Source document",
                "page": page_num,
                "snippet": (
                    page_text[:500]
                    if page_text
                    else (event.get("description", "")[:500])
                ),
                "full_text": page_text or "",
                "term": source_validation_service.extract_highlight_term(
                    description=event.get("description"),
                    snippet=page_text,
                    entity_type="timeline",
                ),
            }

    # Final fallback: if file_id is missing, get first file from case
    if not source_info or not source_info.get("file_id"):
        logger.warning(
            f"[EVIDENCE] file_id not found in source_mapping (FINAL FALLBACK): entity_type={entity_type}, entity_id={entity_id}, trying case files"
        )
        case_file_repo = CaseFileRepository()
        case_files = case_file_repo.list_by_case(db, case_id)
        if case_files:
            first_file = case_files[0]
            logger.info(
                f"[EVIDENCE] Using first case file as final fallback: file_id={first_file.id}, file_name={first_file.file_name}"
            )
            # Build minimal source_info with first file
            source_info = {
                "file_id": first_file.id,
                "file_name": first_file.file_name,
                "page": 1,
                "snippet": f"{entity_type} extracted from case documents",
                "full_text": "",
                "term": None,
            }
            # Try to get term from item if available
            if entity_type == "diagnosis" and index < len(
                extracted_data.get("diagnoses", [])
            ):
                item = extracted_data.get("diagnoses", [])[index]
                if isinstance(item, dict):
                    source_info["term"] = item.get("name")
                    logger.debug(
                        f"[EVIDENCE] Extracted term from diagnosis item: {source_info['term']}"
                    )
            elif entity_type == "medication" and index < len(
                extracted_data.get("medications", [])
            ):
                item = extracted_data.get("medications", [])[index]
                if isinstance(item, dict):
                    source_info["term"] = item.get("name")
                    logger.debug(
                        f"[EVIDENCE] Extracted term from medication item: {source_info['term']}"
                    )
            elif entity_type == "lab" and index < len(extracted_data.get("labs", [])):
                item = extracted_data.get("labs", [])[index]
                if isinstance(item, dict):
                    source_info["term"] = item.get("test_name")
                    logger.debug(
                        f"[EVIDENCE] Extracted term from lab item: {source_info['term']}"
                    )
        else:
            logger.error(f"[EVIDENCE] No case files available: case_id={case_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Source not found for {entity_type}:{entity_id} in case {case_id}. No files available.",
            )

    # Extract highlight term if not set
    if not source_info.get("term"):
        logger.debug(
            f"[EVIDENCE] Extracting highlight term from snippet: snippet_length={len(source_info.get('snippet', '') or '')}"
        )
        source_info["term"] = source_validation_service.extract_highlight_term(
            snippet=source_info.get("snippet"),
            entity_type=entity_type,
        )
        logger.debug(f"[EVIDENCE] Extracted highlight term: {source_info.get('term')}")

    logger.info(
        f"[EVIDENCE] Returning source_info (fallback path): file_id={source_info.get('file_id')}, file_name={source_info.get('file_name')}, page={source_info.get('page')}, has_bbox={source_info.get('bbox') is not None}, has_term={source_info.get('term') is not None}"
    )

    # Track evidence click
    try:
        from app.services.analytics_service import AnalyticsService

        analytics_service = AnalyticsService()
        analytics_service.track_evidence_click(
            db=db,
            user_id=case.user_id,
            case_id=case_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_type="file",
            file_id=source_info.get("file_id"),
            page_number=source_info.get("page"),
        )
        logger.debug(f"[EVIDENCE] Evidence click tracked successfully")
    except Exception as e:
        logger.warning(f"[EVIDENCE] Failed to track evidence click: {e}", exc_info=True)

    return {
        "item": {
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
        "source": source_info,
    }
