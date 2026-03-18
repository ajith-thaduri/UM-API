"""Timeline event source endpoint."""

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_extraction_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.chunk_repository import ChunkRepository
from app.services.entity_source_service import EntitySourceService
from app.services.source_validation_service import source_validation_service

from .deps import get_entity_source_service
from .timeline_helpers import get_timeline_event, resolve_timeline_lab_result_source

logger = logging.getLogger(__name__)

router = APIRouter()


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

    Uses EntitySource when available; falls back to extraction.timeline.
    For lab_result events, resolves correct page/bbox via timeline lab helpers.
    """
    case = case_repository.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    event_id = urllib.parse.unquote(event_id)
    if event_id.startswith("timeline:"):
        event_id = event_id.replace("timeline:", "", 1)

    extraction = extraction_repository.get_by_case_id(db, case_id)
    event = get_timeline_event(extraction, event_id)

    entity_id = f"timeline:{event_id}"
    entity_source = entity_source_service.get_entity_source(
        db=db,
        case_id=case_id,
        entity_type="timeline",
        entity_id=entity_id,
        user_id=case.user_id,
    )

    source_info = None
    item = event or {}

    if entity_source:
        file_name = None
        if entity_source.file_id:
            case_file_repo = CaseFileRepository()
            case_file = case_file_repo.get_by_id(db, entity_source.file_id)
            if case_file:
                file_name = case_file.file_name

        description = (
            event.get("description")
            if isinstance(event, dict)
            else source_validation_service.get_timeline_event_description(db, case_id, event_id)
        )
        highlight_term = source_validation_service.extract_highlight_term(
            description=description, snippet=entity_source.snippet, entity_type="timeline"
        )

        chunk_data = None
        correct_chunk = None
        correct_page = entity_source.page_number or 1
        chunk_repo = ChunkRepository()

        timeline_lab_resolution = resolve_timeline_lab_result_source(
            db=db,
            event=event,
            fallback_file_id=entity_source.file_id,
            fallback_page=correct_page,
            preferred_chunk_id=entity_source.chunk_id,
        )
        if timeline_lab_resolution:
            if timeline_lab_resolution.get("file_id") and not entity_source.file_id:
                entity_source.file_id = timeline_lab_resolution["file_id"]
            if timeline_lab_resolution.get("highlight_term"):
                highlight_term = timeline_lab_resolution["highlight_term"]
            if timeline_lab_resolution.get("bbox"):
                entity_source.bbox = timeline_lab_resolution["bbox"]
            if timeline_lab_resolution.get("correct_chunk"):
                correct_chunk = timeline_lab_resolution["correct_chunk"]
                correct_page = timeline_lab_resolution.get("correct_page") or correct_page
                logger.info(
                    "[EVIDENCE] Timeline lab event %s resolved to page %s via lab-specific matching",
                    event_id,
                    correct_page,
                )

        if entity_source.chunk_id:
            try:
                chunk = chunk_repo.get_by_id(db, entity_source.chunk_id)
                if chunk:
                    entity_term_clean = (highlight_term or "").strip().lower()
                    chunk_text_lower = (chunk.chunk_text or "").lower()
                    if entity_term_clean and entity_term_clean in chunk_text_lower:
                        correct_chunk = chunk
                        correct_page = chunk.page_number
            except Exception as e:
                logger.warning(f"Failed to load chunk: {e}", exc_info=True)

        if not correct_chunk and entity_source.file_id:
            try:
                import re
                all_chunks = chunk_repo.get_by_file_id(db, entity_source.file_id)
                entity_term_clean = (highlight_term or "").strip().lower()

                def normalize_text(text):
                    return re.sub(r"[^a-zA-Z0-9]", "", text.lower())

                if entity_term_clean and all_chunks:
                    norm_entity_term = normalize_text(entity_term_clean)
                    best_match = None
                    best_match_score = 0

                    for chunk in all_chunks:
                        if not chunk.chunk_text:
                            continue
                        chunk_text_lower = chunk.chunk_text.lower()
                        if entity_term_clean in chunk_text_lower:
                            score = 100 + len(entity_term_clean)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue
                        norm_chunk_text = normalize_text(chunk_text_lower)
                        if norm_entity_term in norm_chunk_text:
                            score = 50 + len(norm_entity_term)
                            if score > best_match_score:
                                best_match_score = score
                                best_match = chunk
                                continue
                        words = entity_term_clean.split()
                        if len(words) > 1:
                            match_count = sum(
                                1 for word in words if word in chunk_text_lower and len(word) > 2
                            )
                            if match_count >= len(words) * 0.7:
                                score = match_count * 10
                                if score > best_match_score:
                                    best_match_score = score
                                    best_match = chunk

                    if best_match:
                        correct_chunk = best_match
                        correct_page = best_match.page_number
            except Exception as e:
                logger.warning(f"Failed to search for correct chunk: {e}", exc_info=True)

        if correct_chunk:
            chunk_data = {
                "chunk_id": correct_chunk.id,
                "chunk_text": correct_chunk.chunk_text,
                "char_start": correct_chunk.char_start,
                "char_end": correct_chunk.char_end,
                "section_type": str(correct_chunk.section_type),
                "bbox": correct_chunk.bbox,
            }
            if not getattr(entity_source, "bbox", None) and getattr(correct_chunk, "bbox", None):
                entity_source.bbox = correct_chunk.bbox

        source_info = {
            "file_id": entity_source.file_id,
            "file_name": file_name or item.get("source_file") or (item.get("details") or {}).get("source_file"),
            "page": correct_page,
            "bbox": entity_source.bbox,
            "snippet": entity_source.snippet,
            "full_text": entity_source.full_text,
            "term": highlight_term if highlight_term else None,
            "chunk": chunk_data,
        }

        # OCR provenance for viewer
        if extraction and getattr(extraction, "source_mapping", None):
            ocr_meta_map = extraction.source_mapping.get("ocr_metadata") or {}
            fid = source_info.get("file_id")
            ocr_meta = ocr_meta_map.get(str(fid)) or ocr_meta_map.get(fid)
            if ocr_meta and (source_info.get("page") in ocr_meta.get("ocr_pages", [])):
                source_info["bbox_source"] = "ocr"
                source_info["page_extraction_method"] = "ocr"
                source_info["ocr_confidence"] = ocr_meta.get("document_confidence")
            else:
                source_info["bbox_source"] = "native_pdf"
                source_info["page_extraction_method"] = "native"
                source_info["ocr_confidence"] = None
        else:
            source_info["bbox_source"] = "native_pdf"
            source_info["page_extraction_method"] = "native"
            source_info["ocr_confidence"] = None

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
        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Source not found for timeline event {event_id} in case {case_id}",
            )
        if not event:
            raise HTTPException(
                status_code=404,
                detail=f"Event {event_id} not found in extraction for case {case_id}",
            )

        item = event
        source_file = event.get("source_file") or (event.get("details") or {}).get("source_file")
        source_page = (
            (event.get("details") or {}).get("source_page")
            or event.get("source_page")
            or event.get("page_number")
        )

        if source_file and source_page:
            page_num = int(source_page) if str(source_page).isdigit() else 1
            source_mapping = extraction.source_mapping or {}
            files_list = source_mapping.get("files", [])
            file_id = (event.get("details") or {}).get("source_file_id")
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
            if file_id and isinstance(file_page_mapping, dict) and file_id in file_page_mapping:
                page_mapping = file_page_mapping[file_id]
                if isinstance(page_mapping, dict):
                    page_text = page_mapping.get(page_num, "") or page_mapping.get(str(page_num), "")

            source_info = {
                "file_id": file_id,
                "file_name": source_file,
                "page": page_num,
                "snippet": page_text[:500] if page_text else (event.get("description", "")[:500]),
                "full_text": page_text,
                "term": source_validation_service.extract_highlight_term(
                    description=event.get("description"),
                    snippet=page_text,
                    entity_type="timeline",
                ),
                "bbox": (event.get("details") or {}).get("bbox"),
                "chunk": None,
            }
            # OCR provenance (fallback path)
            source_mapping = extraction.source_mapping or {}
            ocr_meta_map = source_mapping.get("ocr_metadata") or {}
            ocr_meta = ocr_meta_map.get(str(file_id)) or ocr_meta_map.get(file_id)
            if ocr_meta and (page_num in ocr_meta.get("ocr_pages", [])):
                source_info["bbox_source"] = "ocr"
                source_info["page_extraction_method"] = "ocr"
                source_info["ocr_confidence"] = ocr_meta.get("document_confidence")
            else:
                source_info["bbox_source"] = "native_pdf"
                source_info["page_extraction_method"] = "native"
                source_info["ocr_confidence"] = None

            timeline_lab_resolution = resolve_timeline_lab_result_source(
                db=db,
                event=event,
                fallback_file_id=file_id,
                fallback_page=page_num,
            )
            if timeline_lab_resolution:
                source_info["file_id"] = timeline_lab_resolution.get("file_id") or source_info["file_id"]
                source_info["page"] = timeline_lab_resolution.get("correct_page") or source_info["page"]
                source_info["bbox"] = timeline_lab_resolution.get("bbox") or source_info.get("bbox")
                source_info["term"] = timeline_lab_resolution.get("highlight_term") or source_info.get("term")
                resolved_chunk = timeline_lab_resolution.get("correct_chunk")
                if resolved_chunk:
                    source_info["chunk"] = {
                        "chunk_id": resolved_chunk.id,
                        "chunk_text": resolved_chunk.chunk_text,
                        "char_start": resolved_chunk.char_start,
                        "char_end": resolved_chunk.char_end,
                        "section_type": str(resolved_chunk.section_type),
                        "bbox": resolved_chunk.bbox,
                    }

    if not source_info:
        raise HTTPException(
            status_code=404,
            detail=f"Source details not available for timeline event {event_id}",
        )

    # Ensure OCR fields present when not set (e.g. entity_source path already set above)
    if "bbox_source" not in source_info and extraction and getattr(extraction, "source_mapping", None):
        ocr_meta_map = extraction.source_mapping.get("ocr_metadata") or {}
        fid = source_info.get("file_id")
        ocr_meta = ocr_meta_map.get(str(fid)) or ocr_meta_map.get(fid)
        if ocr_meta and (source_info.get("page") in ocr_meta.get("ocr_pages", [])):
            source_info["bbox_source"] = "ocr"
            source_info["page_extraction_method"] = "ocr"
            source_info["ocr_confidence"] = ocr_meta.get("document_confidence")
        else:
            source_info["bbox_source"] = "native_pdf"
            source_info["page_extraction_method"] = "native"
            source_info["ocr_confidence"] = None
    elif "bbox_source" not in source_info:
        source_info["bbox_source"] = "native_pdf"
        source_info["page_extraction_method"] = "native"
        source_info["ocr_confidence"] = None

    return {"item": item or {}, "source": source_info}
