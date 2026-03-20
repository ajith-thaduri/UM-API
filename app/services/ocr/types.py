"""Canonical OCR result types compatible with downstream chunking and source viewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PageExtractionMode(str, Enum):
    """How page text was obtained."""
    NATIVE = "native"   # PDF text layer (pdfplumber)
    OCR = "ocr"        # Full OCR on rasterized page
    MIXED = "mixed"    # Document has both native and OCR pages


@dataclass
class BboxDict:
    """Bounding box in PDF points (x0, y0 top-left; x1, y1 bottom-right)."""
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> Dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> BboxDict:
        return cls(
            x0=float(d.get("x0", 0)),
            y0=float(d.get("y0", 0)),
            x1=float(d.get("x1", 0)),
            y1=float(d.get("y1", 0)),
        )


@dataclass
class TextSegment:
    """Single word/segment with bbox and optional confidence (matches pdfplumber-style downstream)."""
    text: str
    bbox: BboxDict
    char_start: int
    char_end: int
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "char_start": self.char_start,
            "char_end": self.char_end,
        }
        if self.confidence is not None:
            out["confidence"] = self.confidence
        return out


@dataclass
class OCRPageResult:
    """Result for one page: text, word segments, mode, confidence."""
    page_number: int
    text: str
    text_segments: List[TextSegment]
    extraction_mode: PageExtractionMode
    page_confidence: float  # 0.0–1.0
    engine_used: Optional[str] = None  # "tesseract"
    page_width_pt: Optional[float] = None  # PDF page width in points
    page_height_pt: Optional[float] = None  # PDF page height in points

    def to_page_dict(self) -> Dict[str, Any]:
        """Convert to the shape expected by pdf_service / chunking (page_number, text, text_segments)."""
        return {
            "page_number": self.page_number,
            "text": self.text,
            "char_count": len(self.text),
            "text_segments": [s.to_dict() for s in self.text_segments],
            "extraction_mode": self.extraction_mode.value,
            "page_confidence": self.page_confidence,
            "engine_used": self.engine_used,
        }


@dataclass
class OCRDocumentResult:
    """Full document OCR/native extraction result."""
    pages: List[OCRPageResult]
    extraction_method: str  # "pdfplumber", "ocr", "mixed"
    ocr_pages: List[int]  # Page numbers that used OCR
    document_confidence: float  # 0.0–1.0
    ocr_engine_used: Optional[str] = None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_extract_result(self) -> Dict[str, Any]:
        """Convert to the dict shape returned by pdf_service.extract_text_with_coordinates."""
        pages_out = []
        full_text_parts = []
        for p in self.pages:
            d = p.to_page_dict()
            pages_out.append(d)
            full_text_parts.append(f"\n\n--- Page {p.page_number} ---\n\n{p.text}")
        return {
            "text": "".join(full_text_parts),
            "pages": pages_out,
            "page_count": len(pages_out),
            "extraction_method": self.extraction_method,
            "ocr_pages": self.ocr_pages,
            "document_confidence": self.document_confidence,
            "ocr_engine_used": self.ocr_engine_used,
        }
