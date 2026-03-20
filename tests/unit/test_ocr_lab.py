"""Unit tests for OCR Lab service and response contract."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.ocr.lab_service import analyze_pdf_for_lab, get_engine_info


def _native_only_result(page_count=2):
    """Result when all pages have sufficient native text."""
    pages = [
        {
            "page_number": i,
            "text": "This is native text content. " * 5,
            "char_count": 150,
            "text_segments": [{"text": "word", "bbox": {}}] * 10,
        }
        for i in range(1, page_count + 1)
    ]
    return {
        "text": " ".join(p["text"] for p in pages),
        "pages": pages,
        "page_count": page_count,
        "extraction_method": "pdfplumber",
        "ocr_pages": [],
        "document_confidence": 1.0,
    }


def _mixed_result(native_pages=1, ocr_pages_list=None):
    """Result with some native and some OCR pages."""
    if ocr_pages_list is None:
        ocr_pages_list = [2]
    pages = []
    for i in range(1, native_pages + len(ocr_pages_list) + 1):
        is_ocr = i in ocr_pages_list
        pages.append({
            "page_number": i,
            "text": "OCR extracted text here." if is_ocr else "Native text. " * 5,
            "char_count": 25 if is_ocr else 100,
            "text_segments": [{"text": "x", "bbox": {}}] * (3 if is_ocr else 10),
        })
    page_count = len(pages)
    return {
        "text": " ".join(p["text"] for p in pages),
        "pages": pages,
        "page_count": page_count,
        "extraction_method": "mixed",
        "ocr_pages": ocr_pages_list,
        "document_confidence": 0.85,
        "ocr_engine_used": "tesseract",
    }


def _ocr_heavy_result(page_count=2):
    """Result when all pages required OCR."""
    pages = [
        {
            "page_number": i,
            "text": "Scanned page text.",
            "char_count": 20,
            "text_segments": [{"text": "a", "bbox": {}}] * 5,
        }
        for i in range(1, page_count + 1)
    ]
    return {
        "text": " ".join(p["text"] for p in pages),
        "pages": pages,
        "page_count": page_count,
        "extraction_method": "mixed",
        "ocr_pages": list(range(1, page_count + 1)),
        "document_confidence": 0.72,
        "ocr_engine_used": "tesseract",
    }


@patch("app.services.ocr.lab_service.pdf_service")
def test_analyze_pdf_for_lab_native_only(mock_pdf_service):
    """Native-only PDF returns Native text badge and all pages classified as native."""
    mock_pdf_service.extract_text_with_coordinates.return_value = _native_only_result(2)
    result = analyze_pdf_for_lab("/tmp/test.pdf")
    assert result["document_summary"]["document_badge"] == "Native text"
    assert result["document_summary"]["native_page_count"] == 2
    assert result["document_summary"]["ocr_page_count"] == 0
    assert result["document_summary"]["document_confidence"] == 1.0
    assert len(result["pages"]) == 2
    for p in result["pages"]:
        assert p["classification"] == "native"
        assert p["ocr_confidence"] is None
        assert p["engine_used"] is None


@patch("app.services.ocr.lab_service.pdf_service")
def test_analyze_pdf_for_lab_mixed(mock_pdf_service):
    """Mixed PDF returns Mixed OCR badge and correct per-page classification."""
    mock_pdf_service.extract_text_with_coordinates.return_value = _mixed_result(1, [2])
    result = analyze_pdf_for_lab("/tmp/test.pdf")
    assert result["document_summary"]["document_badge"] == "Mixed OCR"
    assert result["document_summary"]["native_page_count"] == 1
    assert result["document_summary"]["ocr_page_count"] == 1
    assert result["document_summary"]["engine_used"] == "tesseract"
    assert result["document_summary"]["document_confidence"] == 0.85
    assert len(result["pages"]) == 2
    assert result["pages"][0]["classification"] == "native"
    assert result["pages"][1]["classification"] == "ocr"
    assert result["pages"][1]["ocr_confidence"] == 0.85
    assert result["pages"][1]["engine_used"] == "tesseract"


@patch("app.services.ocr.lab_service.pdf_service")
def test_analyze_pdf_for_lab_ocr_heavy(mock_pdf_service):
    """All-OCR PDF returns OCR-heavy badge and summary eligibility can be gated."""
    mock_pdf_service.extract_text_with_coordinates.return_value = _ocr_heavy_result(2)
    result = analyze_pdf_for_lab("/tmp/test.pdf")
    assert result["document_summary"]["document_badge"] == "OCR-heavy"
    assert result["document_summary"]["ocr_page_count"] == 2
    assert result["document_summary"]["native_page_count"] == 0
    assert result["document_summary"]["engine_used"] == "tesseract"
    for p in result["pages"]:
        assert p["classification"] == "ocr"
        assert p["ocr_confidence"] == 0.72


@patch("app.services.ocr.lab_service.pdf_service")
def test_analyze_pdf_for_lab_response_shape(mock_pdf_service):
    """Lab response has required document_summary and pages structure."""
    mock_pdf_service.extract_text_with_coordinates.return_value = _native_only_result(1)
    result = analyze_pdf_for_lab("/tmp/test.pdf")
    assert "document_summary" in result
    assert "pages" in result
    summary = result["document_summary"]
    for key in (
        "page_count",
        "document_confidence",
        "summary_eligibility_eligible",
        "summary_eligibility_message",
        "primary_engine",
        "fallback_engine",
        "engine_used",
        "native_page_count",
        "ocr_page_count",
        "document_badge",
        "extraction_method",
    ):
        assert key in summary
    page = result["pages"][0]
    for key in (
        "page_number",
        "classification",
        "native_text_length",
        "ocr_trigger_reason",
        "text",
        "ocr_confidence",
        "engine_used",
        "word_segment_count",
    ):
        assert key in page


@patch("app.services.ocr.lab_service.pdf_service")
def test_analyze_pdf_for_lab_propagates_error(mock_pdf_service):
    """When extraction returns an error, lab response includes it."""
    mock_pdf_service.extract_text_with_coordinates.return_value = {
        "pages": [],
        "page_count": 0,
        "error": "Invalid PDF",
    }
    result = analyze_pdf_for_lab("/tmp/bad.pdf")
    assert result.get("error") == "Invalid PDF"
    assert result["document_summary"]["page_count"] == 0


@patch("app.services.ocr.lab_service._ocr_service_available")
@patch("app.services.ocr.lab_service._fetch_ocr_engines")
def test_get_engine_info_returns_dict(mock_fetch_engines, mock_available):
    """get_engine_info returns dict with OCR service availability and engines list."""
    mock_available.return_value = True
    mock_fetch_engines.return_value = [
        {"id": "tesseract", "name": "Tesseract", "available": True},
        {"id": "ppstructure", "name": "PP-Structure", "available": False},
    ]
    info = get_engine_info()
    assert isinstance(info, dict)
    assert info["primary_engine"] == "ocr_service"
    assert info["primary_available"] is True
    assert info["fallback_engine"] is None
    assert info["fallback_available"] is False
    assert "engines" in info
    assert isinstance(info["engines"], list)
    assert len(info["engines"]) == 2
