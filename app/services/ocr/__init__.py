"""
OCR: page classification, rasterization, coordinate mapping, and OCR service client.
OCR engines run in the standalone OCR service (separate repo); UM-API calls it via HTTP.
"""

from app.services.ocr.types import (
    BboxDict,
    OCRDocumentResult,
    OCRPageResult,
    PageExtractionMode,
    TextSegment,
)
from app.services.ocr.coordinate_mapper import image_bbox_to_pdf, map_segments_to_pdf
from app.services.ocr.pdf_page_rasterizer import rasterize_pdf_page, get_pdf_page_dimensions
from app.services.ocr.page_classifier import page_needs_ocr
from app.services.ocr.confidence import aggregate_document_confidence, summary_eligible

__all__ = [
    "BboxDict",
    "OCRDocumentResult",
    "OCRPageResult",
    "PageExtractionMode",
    "TextSegment",
    "image_bbox_to_pdf",
    "map_segments_to_pdf",
    "rasterize_pdf_page",
    "get_pdf_page_dimensions",
    "page_needs_ocr",
    "aggregate_document_confidence",
    "summary_eligible",
]
