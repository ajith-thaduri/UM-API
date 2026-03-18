"""Legacy get_source route for backward compatibility."""

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_extraction_repository
from app.repositories.case_repository import CaseRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.services.entity_source_service import EntitySourceService
from app.services.source_validation_service import source_validation_service

from .deps import get_entity_source_service

logger = logging.getLogger(__name__)
router = APIRouter()


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
