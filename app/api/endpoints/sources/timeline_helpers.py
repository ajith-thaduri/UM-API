"""
Timeline-specific helpers for resolving event source and lab_result page/bbox.

Used by both the timeline route and the entity_source route when entity_type is timeline.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


def get_timeline_events(extraction) -> list[dict]:
    """Return detailed + summary timeline events from extraction storage."""
    timeline_events = []
    if not extraction:
        return timeline_events

    candidates = [getattr(extraction, "timeline", None)]
    extracted_data = getattr(extraction, "extracted_data", None)
    if isinstance(extracted_data, dict):
        candidates.append(extracted_data.get("timeline"))

    for timeline_data in candidates:
        if isinstance(timeline_data, list):
            timeline_events.extend([e for e in timeline_data if isinstance(e, dict)])
        elif isinstance(timeline_data, dict):
            timeline_events.extend(
                [
                    e
                    for e in (
                        (timeline_data.get("detailed", []) or [])
                        + (timeline_data.get("summary", []) or [])
                    )
                    if isinstance(e, dict)
                ]
            )

    return timeline_events


def get_timeline_event(extraction, event_id: str) -> dict | None:
    """Locate one timeline event by raw or prefixed id."""
    clean_event_id = str(event_id)
    if clean_event_id.startswith("timeline:"):
        clean_event_id = clean_event_id.split(":", 1)[1]

    for event in get_timeline_events(extraction):
        candidate_id = str(event.get("id") or "")
        if (
            candidate_id == clean_event_id
            or candidate_id == f"timeline:{clean_event_id}"
            or candidate_id.endswith(clean_event_id)
        ):
            return event

    return None


def resolve_timeline_lab_result_source(
    db: Session,
    event: dict | None,
    fallback_file_id: str | None = None,
    fallback_page: int | None = None,
    preferred_chunk_id: str | None = None,
) -> dict | None:
    """
    Resolve repeated timeline lab_result events using lab-specific metadata.

    Timeline lab events embed the original extracted lab in `details`, which can
    contain `matching_chunks`, `value`, `date`, `source_file_id`, and `bbox`.
    Reusing that metadata prevents generic name-only matches like "Glucose"
    from jumping to the first occurrence in the file.

    Returns:
        Dict with file_id, correct_page, bbox, highlight_term, correct_chunk,
        or None if event is not a lab_result or details are missing.
    """
    if not isinstance(event, dict) or event.get("event_type") != "lab_result":
        return None

    details = event.get("details")
    if not isinstance(details, dict):
        return None

    from app.repositories.chunk_repository import ChunkRepository
    from app.utils.bbox_utils import find_term_bbox

    def _normalize_page_number(page_value):
        if isinstance(page_value, int):
            return page_value
        if isinstance(page_value, str) and page_value.isdigit():
            return int(page_value)
        return None

    def _date_variants(raw_date: str) -> list[str]:
        value = str(raw_date or "").strip()
        if not value:
            return []
        variants = {value.lower()}
        if "/" in value:
            parts = value.split("/")
            if len(parts) == 3:
                mm, dd, yyyy = parts
                variants.add(f"{mm}/{dd}")
                variants.add(f"{mm.zfill(2)}/{dd.zfill(2)}")
                variants.add(f"{mm}-{dd}-{yyyy}")
                variants.add(f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}")
        return [variant for variant in variants if variant]

    file_id = details.get("source_file_id") or fallback_file_id
    initial_page = (
        _normalize_page_number(details.get("source_page"))
        or _normalize_page_number(event.get("source_page"))
        or _normalize_page_number(event.get("page_number"))
        or fallback_page
        or 1
    )
    initial_bbox = details.get("bbox") if isinstance(details.get("bbox"), dict) else None

    test_name = str(details.get("test_name") or "").strip().lower()
    value = str(details.get("value") or "").strip().lower()
    unit = str(details.get("unit") or "").strip().lower()
    reference_range = str(details.get("reference_range") or "").strip().lower()
    abnormal_flag = str(details.get("abnormal", "")).strip().lower()
    date_variants = _date_variants(str(details.get("date") or "").strip())

    def _score_chunk_text(chunk_text: str) -> int:
        text = (chunk_text or "").lower()
        if not text:
            return -1

        score = 0
        if test_name:
            if test_name in text:
                score += 10
            else:
                return -1
        if value:
            score += 8 if value in text else -4
        if unit and unit in text:
            score += 2
        if reference_range and reference_range in text:
            score += 1
        if abnormal_flag in ("true", "false"):
            abnormal_token = "abnormal" if abnormal_flag == "true" else "normal"
            if abnormal_token in text:
                score += 1
        for date_variant in date_variants:
            if date_variant in text:
                score += 6
                break
        return score

    highlight_term = None
    test_name_raw = str(details.get("test_name") or "").strip()
    value_raw = str(details.get("value") or "").strip()
    date_raw = str(details.get("date") or "").strip()
    unit_raw = str(details.get("unit") or "").strip()
    reference_range_raw = str(details.get("reference_range") or "").strip()

    if test_name_raw and value_raw and date_raw:
        highlight_term = f"{test_name_raw} {value_raw} {date_raw}"
    elif test_name_raw and value_raw:
        highlight_term = f"{test_name_raw} {value_raw}"
    elif test_name_raw:
        highlight_term = test_name_raw

    chunk_repo = ChunkRepository()
    correct_chunk = None
    correct_page = initial_page
    best_score = -10**9

    raw_matching_chunks = details.get("matching_chunks")
    matching_chunk_ids = (
        [str(chunk_id).strip() for chunk_id in raw_matching_chunks if str(chunk_id).strip()]
        if isinstance(raw_matching_chunks, list)
        else []
    )

    seen_chunk_ids = set()

    for chunk_id in matching_chunk_ids:
        chunk_candidate = chunk_repo.get_by_id(db, chunk_id)
        if not chunk_candidate or not chunk_candidate.chunk_text:
            continue
        seen_chunk_ids.add(str(chunk_candidate.id))
        score = _score_chunk_text(chunk_candidate.chunk_text)
        if preferred_chunk_id and chunk_candidate.id == preferred_chunk_id:
            score += 1
        if score > best_score:
            best_score = score
            correct_chunk = chunk_candidate

    # matching_chunks are helpful hints, but timeline events can carry stale or
    # incomplete candidates. Always scan the file as well and keep the highest
    # scoring chunk overall so repeated labs resolve to the exact value/date row.
    if file_id:
        all_chunks = chunk_repo.get_by_file_id(db, file_id)
        for chunk_candidate in all_chunks:
            if not chunk_candidate or not chunk_candidate.chunk_text:
                continue
            if str(chunk_candidate.id) in seen_chunk_ids:
                continue
            score = _score_chunk_text(chunk_candidate.chunk_text)
            if preferred_chunk_id and chunk_candidate.id == preferred_chunk_id:
                score += 1
            if score > best_score:
                best_score = score
                correct_chunk = chunk_candidate

    precise_bbox = None
    if correct_chunk:
        correct_page = correct_chunk.page_number or correct_page
        file_id = correct_chunk.file_id or file_id
        terms_to_try = []
        if test_name_raw and value_raw and date_raw:
            terms_to_try.append(f"{test_name_raw} {value_raw} {date_raw}")
            terms_to_try.append(f"{test_name_raw} {date_raw} {value_raw}")
        if test_name_raw and value_raw and unit_raw:
            terms_to_try.append(f"{test_name_raw} {value_raw} {unit_raw}")
        if test_name_raw and value_raw and reference_range_raw:
            terms_to_try.append(f"{test_name_raw} {value_raw} {reference_range_raw}")
        if test_name_raw and value_raw:
            terms_to_try.append(f"{test_name_raw} {value_raw}")
        if test_name_raw:
            terms_to_try.append(test_name_raw)

        seen_terms = set()
        ordered_terms = []
        for term in terms_to_try:
            if term and term not in seen_terms:
                ordered_terms.append(term)
                seen_terms.add(term)

        if getattr(correct_chunk, "word_segments", None):
            for term in ordered_terms:
                precise_bbox = find_term_bbox(term, correct_chunk.word_segments)
                if precise_bbox:
                    break

        if not precise_bbox and getattr(correct_chunk, "bbox", None):
            precise_bbox = correct_chunk.bbox

    if not precise_bbox and initial_bbox and correct_page == initial_page:
        precise_bbox = initial_bbox

    return {
        "file_id": file_id,
        "correct_page": correct_page,
        "bbox": precise_bbox,
        "highlight_term": highlight_term,
        "correct_chunk": correct_chunk,
    }
