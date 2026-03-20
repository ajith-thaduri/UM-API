"""Map OCR bounding boxes from image pixel space to PDF point space."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.ocr.types import BboxDict, TextSegment


def image_bbox_to_pdf(
    image_width_px: float,
    image_height_px: float,
    page_width_pt: float,
    page_height_pt: float,
    bbox: Dict[str, float],
) -> BboxDict:
    """
    Convert a bbox from image pixel coordinates to PDF points (same convention as pdfplumber).

    Assumes image is rendered from PDF with same aspect ratio or scaled uniformly;
    uses scale factors so that (0,0) is top-left and coordinates map linearly.

    Args:
        image_width_px: Width of the rasterized image in pixels.
        image_height_px: Height of the rasterized image in pixels.
        page_width_pt: PDF page width in points (e.g. 612).
        page_height_pt: PDF page height in points (e.g. 792).
        bbox: Dict with x0, y0, x1, y1 in image pixels (top-left origin).

    Returns:
        BboxDict in PDF point space (x0, y0 top-left; x1, y1 bottom-right).
    """
    if image_width_px <= 0 or image_height_px <= 0:
        return BboxDict(x0=0, y0=0, x1=page_width_pt, y1=page_height_pt)
    scale_x = page_width_pt / image_width_px
    scale_y = page_height_pt / image_height_px
    return BboxDict(
        x0=bbox["x0"] * scale_x,
        y0=bbox["y0"] * scale_y,
        x1=bbox["x1"] * scale_x,
        y1=bbox["y1"] * scale_y,
    )


def map_segments_to_pdf(
    image_width_px: float,
    image_height_px: float,
    page_width_pt: float,
    page_height_pt: float,
    raw_segments: List[Dict[str, Any]],
) -> List[TextSegment]:
    """
    Convert a list of raw OCR segments (image-space bbox) to TextSegments in PDF space,
    with char_start/char_end set in reading order.
    """
    segments: List[TextSegment] = []
    char_pos = 0
    for raw in raw_segments:
        text = raw.get("text", "").strip()
        if not text:
            continue
        bbox_raw = raw.get("bbox")
        if not bbox_raw:
            continue
        pdf_bbox = image_bbox_to_pdf(
            image_width_px, image_height_px,
            page_width_pt, page_height_pt,
            bbox_raw,
        )
        seg = TextSegment(
            text=text,
            bbox=pdf_bbox,
            char_start=char_pos,
            char_end=char_pos + len(text),
            confidence=raw.get("confidence"),
        )
        segments.append(seg)
        char_pos += len(text) + 1
    return segments
